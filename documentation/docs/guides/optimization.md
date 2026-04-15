# Apply Optimizations

`apply()` transforms the in-memory circuit with one of the registered methods.
The available methods are exported by the package:

```python
from thermalbits import DEPTH_ORIENTED, ENERGY_ORIENTED, ThermalBits
```

## Methods

| Constant | Method | Goal |
|---|---|---|
| `ENERGY_ORIENTED` | Energy-oriented (EO) | Maximize energy reduction, allowing circuit depth to increase. |
| `DEPTH_ORIENTED` | Depth-oriented / Delay-oriented (DO) | Reduce energy while preserving the original circuit depth. |

## Apply a transformation

`apply()` mutates the object and returns the same instance.

```python
from thermalbits import ENERGY_ORIENTED, ThermalBits

tb = ThermalBits("test_files/half_adder.v")
tb.apply(ENERGY_ORIENTED)
```

To keep the original circuit:

```python
from thermalbits import DEPTH_ORIENTED, ENERGY_ORIENTED, ThermalBits

original = ThermalBits("test_files/half_adder.v")

depth_tb = original.copy().apply(DEPTH_ORIENTED)
energy_tb = original.copy().apply(ENERGY_ORIENTED)
```

## Compare energy

```python
from thermalbits import ENERGY_ORIENTED, ThermalBits

original = ThermalBits("test_files/half_adder.v")
optimized = original.copy().apply(ENERGY_ORIENTED)

original_energy = original.update_entropy(chunks=None)
optimized_energy = optimized.update_entropy(chunks=None)

print(original_energy)
print(optimized_energy)
```

## Half adder comparison

The table below uses `test_files/half_adder.v` and `update_entropy(chunks=None)`.

| Circuit | Gates | Levels | Energy (bits) |
|---|---:|---:|---:|
| Original | 5 | 3 | 3.754888 |
| Energy-oriented | 5 | 5 | 0.688722 |
| Depth-oriented | 5 | 3 | 1.877444 |

### Original

![Original half adder DAG](../assets/images/half_adder_original.png)

### Energy-oriented

![Energy-oriented half adder DAG](../assets/images/half_adder_energy_oriented.png)

### Depth-oriented

![Depth-oriented half adder DAG](../assets/images/half_adder_depth_oriented.png)

## Export the optimized circuit

```python
optimized.write_json("half_adder_eo.json")
optimized.write_verilog("half_adder_eo.v", module_name="half_adder_eo")
optimized.visualize_dag("half_adder_eo.png", orientation="horizontal")
```
