import type { CSSProperties, Ref } from "react";

export type AnimacaoSabia = "piscar" | "assobiar" | "agachar" | "levantar" | "chacoalhar";

export interface ResultadoAnimacao { animacao: AnimacaoSabia; cancelada: boolean }

export declare class SabiaSelo extends HTMLElement {
  readonly postura: "em-pe" | "agachado";
  readonly animando: boolean;
  play(nome: AnimacaoSabia): Promise<ResultadoAnimacao>;
  piscar(): Promise<ResultadoAnimacao>;
  assobiar(): Promise<ResultadoAnimacao>;
  agachar(): Promise<ResultadoAnimacao>;
  levantar(): Promise<ResultadoAnimacao>;
  chacoalhar(): Promise<ResultadoAnimacao>;
}

export declare const ANIMACOES: Readonly<Record<AnimacaoSabia, { canal: string; alvo: string; nome: string; duracao: number }>>;
export declare function registrarSabiaSelo(tag?: string): void;

declare global {
  namespace JSX {
    interface IntrinsicElements {
      "sabia-selo": {
        ref?: Ref<SabiaSelo>;
        tamanho?: string | number;
        ocioso?: "" | undefined;
        decorativo?: "" | undefined;
        rotulo?: string;
        "movimento-reduzido"?: "" | undefined;
        class?: string;
        style?: CSSProperties;
      };
    }
  }
}
