<?php
// Imprime, em JSON, os tokens de um arquivo PHP que um leitor humano (ou um
// LLM) veria como texto: comentarios, nomes, variaveis, strings e HTML inline.
$codigo = file_get_contents($argv[1]);
$saida = [];
$tokens = token_get_all($codigo);
$anterior = null;
foreach ($tokens as $t) {
    if (!is_array($t)) { if (trim($t) !== '') $anterior = $t; continue; }
    [$id, $texto, $linha] = $t;
    $nome = token_name($id);
    if (in_array($nome, ['T_COMMENT', 'T_DOC_COMMENT', 'T_VARIABLE', 'T_CONSTANT_ENCAPSED_STRING',
                         'T_ENCAPSED_AND_WHITESPACE', 'T_INLINE_HTML', 'T_STRING', 'T_NAME_QUALIFIED',
                         'T_NAME_FULLY_QUALIFIED', 'T_GOTO'])) {
        $decl = null;
        if ($nome === 'T_STRING' && is_array($anterior)) {
            $p = token_name($anterior[0]);
            if (in_array($p, ['T_FUNCTION', 'T_CLASS', 'T_CONST', 'T_INTERFACE', 'T_TRAIT', 'T_EXTENDS', 'T_NEW'])) $decl = $p;
        }
        $saida[] = ['tipo' => $nome, 'texto' => $texto, 'linha' => $linha, 'decl' => $decl];
    }
    if ($id !== T_WHITESPACE) $anterior = $t;
}
echo json_encode($saida, JSON_UNESCAPED_UNICODE);
