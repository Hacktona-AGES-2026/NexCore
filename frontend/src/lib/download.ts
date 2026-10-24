/**
 * Baixa um texto como arquivo, com o nome certo em qualquer navegador.
 *
 * O link precisa estar na página na hora do clique (Firefox ignora o
 * `download` de link solto) e o endereço do blob só pode ser liberado depois
 * que o download começou; liberar na hora faz alguns navegadores salvarem
 * com nome aleatório e sem extensão.
 *
 * `bom` põe a marca UTF-8 no início para o Excel abrir os acentos certos.
 * Não use no fila_priorizada.csv: o verificador oficial espera UTF-8 sem BOM.
 */
export function downloadText(filename: string, text: string, { type = "text/csv;charset=utf-8", bom = false } = {}) {
  const blob = new Blob([bom ? "﻿" : "", text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
