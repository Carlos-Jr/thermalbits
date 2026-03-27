//! Objetivo: iniciar o binario e delegar a execucao para a biblioteca.
//! Entradas: argumentos do processo recebidos via linha de comando.
//! Saidas: chamada da camada `app` com o comando parseado.

use circuit_sim::{app, cli};

fn main() {
    let command = cli::parse_args();
    app::run(command);
}
