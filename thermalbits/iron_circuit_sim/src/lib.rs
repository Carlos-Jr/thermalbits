//! Objetivo: expor a organizacao modular da aplicacao de simulacao.
//! Entradas: comandos parseados da CLI e arquivos de circuito/partials no disco.
//! Saidas: funcoes reutilizaveis para executar simulacao, merge e relatorios.

pub mod app;
pub mod circuit;
pub mod cli;
pub mod io;
pub mod sim;
pub mod stats;
