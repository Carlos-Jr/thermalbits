//! Objetivo: portar para Rust os algoritmos de cadeia de fanout EO/DO aplicados ao overview.
//! Entradas: `Overview` com PIs, POs e nodes validados; politica de selecao (EO ou DO).
//! Saidas: `Overview` mutado com a cadeia aplicada, niveis e suporte recalculados em paralelo.

use std::cmp::Reverse;
use std::collections::{BTreeMap, BTreeSet, BinaryHeap, VecDeque};

use rayon::prelude::*;

use crate::model::{FanoutEntry, Node, Overview, SUPPORTED_OPS, WIRE_OP};

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Policy {
    DepthOriented,
    EnergyOriented,
}

type NodeMap = BTreeMap<u32, Node>;
type ChildrenIndex = BTreeMap<(u32, u32), BTreeSet<u32>>;
type NodeChildren = BTreeMap<u32, BTreeSet<u32>>;
type NodePreds = BTreeMap<u32, BTreeSet<u32>>;

pub fn apply(overview: &mut Overview, policy: Policy) -> Result<(), String> {
    let preserve_depth = policy == Policy::DepthOriented;

    let pis = overview.pis.clone();
    let pos = overview.pos.clone();

    let taken_nodes = std::mem::take(&mut overview.nodes);

    validate_nodes_parallel(&taken_nodes)?;

    let mut node_by_id: NodeMap = BTreeMap::new();
    for n in taken_nodes {
        if node_by_id.insert(n.id, n).is_some() {
            return Err(format!("Duplicated node id in overview"));
        }
    }

    let pi_set: BTreeSet<u32> = pis.iter().copied().collect();
    for &pi in &pis {
        if node_by_id.contains_key(&pi) {
            return Err(format!("Primary inputs and nodes share IDs: {}", pi));
        }
    }
    for &po in &pos {
        if !pi_set.contains(&po) && !node_by_id.contains_key(&po) {
            return Err(format!("Overview output id has no source signal: {}", po));
        }
    }

    let max_allowed_depth = if preserve_depth {
        Some(current_depth(&node_by_id))
    } else {
        None
    };

    let mut children_index = build_children_index(&pis, &node_by_id);
    let ordered_source_refs = sorted_source_refs(&children_index, &node_by_id);

    let (mut current, mut node_children, mut node_preds) =
        rebuild_level_state(&pis, &mut node_by_id);

    for source_ref in ordered_source_refs {
        let mut used_children: BTreeSet<u32> = BTreeSet::new();

        loop {
            let ordered_choices =
                collect_ordered_choices(&source_ref, &children_index, &node_by_id, &used_children, policy);

            if ordered_choices.len() <= 1 {
                break;
            }

            let snapshot = if preserve_depth {
                Some(snapshot_nodes(&ordered_choices, &node_by_id))
            } else {
                None
            };

            let (changed, rewired) = make_chain(&source_ref, &ordered_choices, &mut node_by_id);

            if !changed {
                for id in &ordered_choices {
                    used_children.insert(*id);
                }
                break;
            }

            refresh_dependency_index_for_nodes(
                &rewired,
                &pis,
                &node_by_id,
                &mut node_children,
                &mut node_preds,
            );
            current = propagate_levels(&rewired, &pis, &mut node_by_id, &node_children, current);

            if let Some(max_d) = max_allowed_depth {
                if current > max_d {
                    let snap = snapshot.expect("snapshot missing for depth-preserving rollback");
                    restore_nodes(snap, &mut node_by_id);
                    let (c, ch, pr) = rebuild_level_state(&pis, &mut node_by_id);
                    current = c;
                    node_children = ch;
                    node_preds = pr;
                    break;
                }
            }

            if let Some(set) = children_index.get_mut(&source_ref) {
                for id in &rewired {
                    set.remove(id);
                }
            }
            for id in &ordered_choices {
                used_children.insert(*id);
            }
        }
    }

    recompute_levels_and_support(&pis, &mut node_by_id);

    let mut nodes_out: Vec<Node> = node_by_id.into_values().collect();
    nodes_out.sort_by_key(|n| n.id);
    overview.nodes = nodes_out;
    Ok(())
}

fn validate_nodes_parallel(nodes: &[Node]) -> Result<(), String> {
    let errors: Vec<String> = nodes
        .par_iter()
        .filter_map(|node| validate_node(node).err())
        .collect();
    if let Some(first) = errors.into_iter().next() {
        return Err(first);
    }
    Ok(())
}

fn validate_node(node: &Node) -> Result<(), String> {
    if node.fanout.is_empty() {
        return Err(format!("Node {} field 'fanout' must be a non-empty list", node.id));
    }
    for (fo_idx, fo) in node.fanout.iter().enumerate() {
        if fo.input.len() != fo.invert.len() {
            return Err(format!(
                "Node {} fanout[{}] fields 'input' and 'invert' must have the same length",
                node.id, fo_idx
            ));
        }
        if !SUPPORTED_OPS.contains(&fo.op.as_str()) {
            return Err(format!(
                "Unsupported node operator for id {} fanout[{}]: {}",
                node.id, fo_idx, fo.op
            ));
        }
        for &inv in &fo.invert {
            if inv > 1 {
                return Err(format!(
                    "Node {} fanout[{}] has invalid invert flag: {}",
                    node.id, fo_idx, inv
                ));
            }
        }
        for &idx in &fo.input {
            if idx >= node.fanin.len() {
                return Err(format!(
                    "Node {} fanout[{}] references invalid fanin index",
                    node.id, fo_idx
                ));
            }
        }
    }
    Ok(())
}

fn current_depth(node_by_id: &NodeMap) -> u32 {
    node_by_id.values().map(|n| n.level).max().unwrap_or(0)
}

fn source_level(source_ref: &(u32, u32), node_by_id: &NodeMap) -> u32 {
    match node_by_id.get(&source_ref.0) {
        Some(n) => n.level,
        None => 0,
    }
}

fn build_children_index(pis: &[u32], node_by_id: &NodeMap) -> ChildrenIndex {
    let mut valid_sources: BTreeSet<(u32, u32)> = BTreeSet::new();
    for &pi in pis {
        valid_sources.insert((pi, 0));
    }
    for (&id, node) in node_by_id.iter() {
        for (idx, fo) in node.fanout.iter().enumerate() {
            if fo.op != WIRE_OP {
                valid_sources.insert((id, idx as u32));
            }
        }
    }

    let per_node_edges: Vec<Vec<((u32, u32), u32)>> = node_by_id
        .values()
        .par_bridge()
        .map(|node| {
            let child_id = node.id;
            let mut edges = Vec::with_capacity(node.fanin.len());
            for r in &node.fanin {
                let src_ref = (r[0], r[1]);
                if valid_sources.contains(&src_ref) {
                    edges.push((src_ref, child_id));
                }
            }
            edges
        })
        .collect();

    let mut index: ChildrenIndex = BTreeMap::new();
    for src in &valid_sources {
        index.insert(*src, BTreeSet::new());
    }
    for edges in per_node_edges {
        for (src_ref, child_id) in edges {
            if let Some(set) = index.get_mut(&src_ref) {
                set.insert(child_id);
            }
        }
    }
    index
}

fn sorted_source_refs(children_index: &ChildrenIndex, node_by_id: &NodeMap) -> Vec<(u32, u32)> {
    let mut refs: Vec<(u32, u32)> = children_index.keys().copied().collect();
    refs.sort_by(|a, b| {
        let la = source_level(a, node_by_id);
        let lb = source_level(b, node_by_id);
        (lb, b.0, b.1).cmp(&(la, a.0, a.1))
    });
    refs
}

fn ranked_children(
    source_ref: &(u32, u32),
    children_index: &ChildrenIndex,
    node_by_id: &NodeMap,
) -> Vec<(u32, Vec<u32>)> {
    let empty: BTreeSet<u32> = BTreeSet::new();
    let children = children_index.get(source_ref).unwrap_or(&empty);
    let mut grouped: BTreeMap<u32, Vec<u32>> = BTreeMap::new();
    for &child_id in children {
        let level = node_by_id[&child_id].level;
        grouped.entry(level).or_default().push(child_id);
    }
    grouped
        .into_iter()
        .map(|(level, mut ids)| {
            ids.sort();
            (level, ids)
        })
        .collect()
}

fn choose(grouped: &[u32], used_children: &BTreeSet<u32>, policy: Policy) -> Vec<u32> {
    let valid: Vec<u32> = grouped
        .iter()
        .copied()
        .filter(|id| !used_children.contains(id))
        .collect();
    match policy {
        Policy::DepthOriented => valid.into_iter().take(1).collect(),
        Policy::EnergyOriented => valid,
    }
}

fn collect_ordered_choices(
    source_ref: &(u32, u32),
    children_index: &ChildrenIndex,
    node_by_id: &NodeMap,
    used_children: &BTreeSet<u32>,
    policy: Policy,
) -> Vec<u32> {
    let mut flat: Vec<u32> = Vec::new();
    for (_level, grouped) in ranked_children(source_ref, children_index, node_by_id) {
        flat.extend(choose(&grouped, used_children, policy));
    }
    let unique: BTreeSet<u32> = flat.into_iter().collect();
    let mut ordered: Vec<u32> = unique.into_iter().collect();
    ordered.sort_by_key(|id| (node_by_id[id].level, *id));
    ordered
}

fn add_wire_fanout(node: &mut Node, local_fanin_idx: usize) -> usize {
    for (i, entry) in node.fanout.iter().enumerate() {
        if entry.op == WIRE_OP
            && entry.input.len() == 1
            && entry.input[0] == local_fanin_idx
            && entry.invert.len() == 1
            && entry.invert[0] == 0
        {
            return i;
        }
    }
    let new_idx = node.fanout.len();
    node.fanout.push(FanoutEntry {
        input: vec![local_fanin_idx],
        invert: vec![0],
        op: WIRE_OP.to_string(),
    });
    new_idx
}

fn normalize_node_fanin(node: &mut Node) {
    if node.fanin.is_empty() {
        return;
    }

    let mut deduped: Vec<[u32; 2]> = Vec::with_capacity(node.fanin.len());
    let mut ref_to_index: BTreeMap<(u32, u32), usize> = BTreeMap::new();
    let mut remap: Vec<usize> = Vec::with_capacity(node.fanin.len());

    for r in &node.fanin {
        let key = (r[0], r[1]);
        let idx = match ref_to_index.get(&key) {
            Some(&i) => i,
            None => {
                let i = deduped.len();
                ref_to_index.insert(key, i);
                deduped.push([r[0], r[1]]);
                i
            }
        };
        remap.push(idx);
    }

    if deduped.len() == node.fanin.len() {
        return;
    }

    node.fanin = deduped;
    for fo in node.fanout.iter_mut() {
        fo.input = fo.input.iter().map(|&i| remap[i]).collect();
    }
}

fn make_chain(
    source_ref: &(u32, u32),
    choices: &[u32],
    node_by_id: &mut NodeMap,
) -> (bool, BTreeSet<u32>) {
    let mut rewired: BTreeSet<u32> = BTreeSet::new();
    if choices.is_empty() {
        return (false, rewired);
    }

    let mut changed = false;
    let mut previous_id: Option<u32> = None;
    let mut carry_fanin_idx: Option<usize> = None;

    for (index, &child_id) in choices.iter().enumerate() {
        if index == 0 {
            let child = node_by_id.get(&child_id).expect("child must exist");
            for (k, r) in child.fanin.iter().enumerate() {
                if r[0] == source_ref.0 && r[1] == source_ref.1 {
                    carry_fanin_idx = Some(k);
                    break;
                }
            }
        } else {
            let (prev_id, carry_idx) = match (previous_id, carry_fanin_idx) {
                (Some(p), Some(c)) => (p, c),
                _ => {
                    previous_id = Some(child_id);
                    continue;
                }
            };

            let wire_idx = {
                let prev = node_by_id.get_mut(&prev_id).expect("previous must exist");
                add_wire_fanout(prev, carry_idx)
            };
            let wire_idx_u32 = wire_idx as u32;

            let child = node_by_id.get_mut(&child_id).expect("child must exist");
            let mut rewired_any = false;
            for r in child.fanin.iter_mut() {
                if r[0] == source_ref.0 && r[1] == source_ref.1 {
                    r[0] = prev_id;
                    r[1] = wire_idx_u32;
                    changed = true;
                    rewired_any = true;
                }
            }
            if rewired_any {
                rewired.insert(child_id);
            }

            normalize_node_fanin(child);

            carry_fanin_idx = None;
            for (k, r) in child.fanin.iter().enumerate() {
                if r[0] == prev_id && r[1] == wire_idx_u32 {
                    carry_fanin_idx = Some(k);
                    break;
                }
            }
        }
        previous_id = Some(child_id);
    }

    (changed, rewired)
}

fn node_predecessor_ids(node: &Node, pi_set: &BTreeSet<u32>, node_by_id: &NodeMap) -> BTreeSet<u32> {
    let mut preds: BTreeSet<u32> = BTreeSet::new();
    for r in &node.fanin {
        let src_id = r[0];
        let out_idx = r[1];
        if pi_set.contains(&src_id) {
            if out_idx != 0 {
                panic!(
                    "Node {} references primary input {} with invalid output index {}",
                    node.id, src_id, out_idx
                );
            }
            continue;
        }
        let src = node_by_id.get(&src_id).unwrap_or_else(|| {
            panic!("Node {} references unknown fanin id: {}", node.id, src_id)
        });
        if out_idx as usize >= src.fanout.len() {
            panic!(
                "Node {} references node {} output index {}, but that node has only {} outputs",
                node.id, src_id, out_idx, src.fanout.len()
            );
        }
        preds.insert(src_id);
    }
    preds
}

fn build_dependency_index(pis: &[u32], node_by_id: &NodeMap) -> (NodeChildren, NodePreds) {
    let pi_set: BTreeSet<u32> = pis.iter().copied().collect();

    let per_node_preds: Vec<(u32, BTreeSet<u32>)> = node_by_id
        .values()
        .par_bridge()
        .map(|node| (node.id, node_predecessor_ids(node, &pi_set, node_by_id)))
        .collect();

    let mut children_by_id: NodeChildren = BTreeMap::new();
    for &id in node_by_id.keys() {
        children_by_id.insert(id, BTreeSet::new());
    }
    let mut preds_by_id: NodePreds = BTreeMap::new();

    for (node_id, preds) in per_node_preds {
        for &src in &preds {
            if let Some(set) = children_by_id.get_mut(&src) {
                set.insert(node_id);
            }
        }
        preds_by_id.insert(node_id, preds);
    }

    (children_by_id, preds_by_id)
}

fn topological_node_ids(children_by_id: &NodeChildren, indegree: &mut BTreeMap<u32, usize>) -> Vec<u32> {
    let total = indegree.len();
    let mut ready: BinaryHeap<Reverse<u32>> = BinaryHeap::new();
    for (&id, &count) in indegree.iter() {
        if count == 0 {
            ready.push(Reverse(id));
        }
    }

    let mut ordered = Vec::with_capacity(total);
    while let Some(Reverse(node_id)) = ready.pop() {
        ordered.push(node_id);
        if let Some(children) = children_by_id.get(&node_id) {
            for &child_id in children {
                let count = indegree.get_mut(&child_id).expect("missing indegree");
                *count -= 1;
                if *count == 0 {
                    ready.push(Reverse(child_id));
                }
            }
        }
    }

    if ordered.len() != total {
        panic!("Transformation created a cycle in the circuit overview");
    }
    ordered
}

fn computed_node_level(node: &Node, pi_set: &BTreeSet<u32>, node_by_id: &NodeMap) -> u32 {
    if node.fanin.is_empty() {
        return 0;
    }
    let mut max_pred = 0;
    for r in &node.fanin {
        if pi_set.contains(&r[0]) {
            continue;
        }
        let level = node_by_id[&r[0]].level;
        if level > max_pred {
            max_pred = level;
        }
    }
    max_pred + 1
}

fn rebuild_level_state(pis: &[u32], node_by_id: &mut NodeMap) -> (u32, NodeChildren, NodePreds) {
    let (children_by_id, preds_by_id) = build_dependency_index(pis, node_by_id);
    let mut indegree: BTreeMap<u32, usize> = preds_by_id
        .iter()
        .map(|(&id, set)| (id, set.len()))
        .collect();
    let ordered = topological_node_ids(&children_by_id, &mut indegree);

    let pi_set: BTreeSet<u32> = pis.iter().copied().collect();
    let mut max_depth = 0;
    for node_id in ordered {
        let level = {
            let node = node_by_id.get(&node_id).expect("node must exist");
            computed_node_level(node, &pi_set, node_by_id)
        };
        let node = node_by_id.get_mut(&node_id).expect("node must exist");
        node.level = level;
        if level > max_depth {
            max_depth = level;
        }
    }

    (max_depth, children_by_id, preds_by_id)
}

fn refresh_dependency_index_for_nodes(
    node_ids: &BTreeSet<u32>,
    pis: &[u32],
    node_by_id: &NodeMap,
    children_by_id: &mut NodeChildren,
    preds_by_id: &mut NodePreds,
) {
    let pi_set: BTreeSet<u32> = pis.iter().copied().collect();
    for &node_id in node_ids {
        let node = node_by_id.get(&node_id).expect("node must exist");
        let new_preds = node_predecessor_ids(node, &pi_set, node_by_id);
        let old_preds = preds_by_id.get(&node_id).cloned().unwrap_or_default();

        for removed_id in old_preds.difference(&new_preds) {
            if let Some(set) = children_by_id.get_mut(removed_id) {
                set.remove(&node_id);
            }
        }
        for added_id in new_preds.difference(&old_preds) {
            children_by_id.entry(*added_id).or_default().insert(node_id);
        }

        preds_by_id.insert(node_id, new_preds);
    }
}

fn propagate_levels(
    start_ids: &BTreeSet<u32>,
    pis: &[u32],
    node_by_id: &mut NodeMap,
    children_by_id: &NodeChildren,
    current_depth: u32,
) -> u32 {
    let pi_set: BTreeSet<u32> = pis.iter().copied().collect();

    let mut seeds: Vec<u32> = start_ids.iter().copied().collect();
    seeds.sort_by_key(|&id| (node_by_id[&id].level, id));

    let mut queue: VecDeque<u32> = VecDeque::from(seeds.clone());
    let mut queued: BTreeSet<u32> = seeds.into_iter().collect();
    let mut max_depth = current_depth;

    while let Some(node_id) = queue.pop_front() {
        queued.remove(&node_id);

        let old_level = node_by_id[&node_id].level;
        let new_level = {
            let node = node_by_id.get(&node_id).expect("node must exist");
            computed_node_level(node, &pi_set, node_by_id)
        };
        if new_level == old_level {
            continue;
        }

        node_by_id.get_mut(&node_id).expect("node must exist").level = new_level;
        if new_level > max_depth {
            max_depth = new_level;
        }

        if let Some(children) = children_by_id.get(&node_id) {
            for &child_id in children {
                if !queued.contains(&child_id) {
                    queue.push_back(child_id);
                    queued.insert(child_id);
                }
            }
        }
    }

    max_depth
}

fn recompute_levels_and_support(pis: &[u32], node_by_id: &mut NodeMap) {
    let (children_by_id, preds_by_id) = build_dependency_index(pis, node_by_id);
    let mut indegree: BTreeMap<u32, usize> = preds_by_id
        .iter()
        .map(|(&id, set)| (id, set.len()))
        .collect();
    let ordered = topological_node_ids(&children_by_id, &mut indegree);

    let pi_set: BTreeSet<u32> = pis.iter().copied().collect();

    // Agrupa nos por onda (level) usando os niveis ja computados em ordem topologica,
    // para processar cada onda em paralelo sem conflitos de dependencia.
    let mut wave_of: BTreeMap<u32, u32> = BTreeMap::new();
    for &node_id in &ordered {
        let node = &node_by_id[&node_id];
        let mut w: u32 = 0;
        if !node.fanin.is_empty() {
            let mut max_pred: Option<u32> = None;
            for r in &node.fanin {
                if !pi_set.contains(&r[0]) {
                    if let Some(&pw) = wave_of.get(&r[0]) {
                        max_pred = Some(max_pred.map_or(pw, |m| m.max(pw)));
                    }
                }
            }
            w = max_pred.map_or(1, |m| m + 1);
        }
        wave_of.insert(node_id, w);
    }

    let mut waves: BTreeMap<u32, Vec<u32>> = BTreeMap::new();
    for (&id, &w) in &wave_of {
        waves.entry(w).or_default().push(id);
    }

    let mut level_by_id: BTreeMap<u32, u32> = BTreeMap::new();
    let mut support_by_id: BTreeMap<u32, Vec<u32>> = BTreeMap::new();

    for (_wave, bucket) in waves.iter() {
        let results: Vec<(u32, u32, Vec<u32>)> = bucket
            .par_iter()
            .map(|&node_id| {
                let node = &node_by_id[&node_id];
                let mut max_pred_level: u32 = 0;
                let mut support_set: BTreeSet<u32> = BTreeSet::new();
                for r in &node.fanin {
                    let src = r[0];
                    if pi_set.contains(&src) {
                        support_set.insert(src);
                    } else {
                        let lvl = *level_by_id.get(&src).expect("predecessor level missing");
                        if lvl > max_pred_level {
                            max_pred_level = lvl;
                        }
                        if let Some(s) = support_by_id.get(&src) {
                            for v in s {
                                support_set.insert(*v);
                            }
                        }
                    }
                }
                let level = if node.fanin.is_empty() { 0 } else { max_pred_level + 1 };
                let support_sorted: Vec<u32> = support_set.into_iter().collect();
                (node_id, level, support_sorted)
            })
            .collect();

        for (id, lvl, sup) in results {
            let node = node_by_id.get_mut(&id).expect("node must exist");
            node.level = lvl;
            node.suport = sup.clone();
            level_by_id.insert(id, lvl);
            support_by_id.insert(id, sup);
        }
    }
}

fn snapshot_nodes(node_ids: &[u32], node_by_id: &NodeMap) -> Vec<(u32, Node)> {
    node_ids
        .iter()
        .map(|&id| (id, node_by_id[&id].clone()))
        .collect()
}

fn restore_nodes(snapshot: Vec<(u32, Node)>, node_by_id: &mut NodeMap) {
    for (id, node) in snapshot {
        node_by_id.insert(id, node);
    }
}
