
  CREATE OR REPLACE EDITIONABLE PROCEDURE "JOSEGOMES"."PRC_CARREGA_NOVOS_FUNC" (p_ano NUMBER, p_mes NUMBER) AS
    v_sql CLOB;
BEGIN
    -- Limpa a tabela temporária antes da nova carga
    EXECUTE IMMEDIATE 'TRUNCATE TABLE GTT_NOVOS_FUNCIONARIOS';

    FOR r IN (SELECT owner
                FROM all_tables
               WHERE table_name = 'FOLHA_FUNC'
                 AND owner LIKE 'SW_%'
                 AND owner NOT IN ('SW_PUBLICO', 'SW_MODELO'))
    LOOP
        -- Montagem do SQL dinâmico com a nova regra de NOT EXISTS por vínculo
        v_sql := 'INSERT INTO GTT_NOVOS_FUNCIONARIOS
        SELECT
            ''' || REPLACE(r.owner, 'SW_', '') || ''',
            fo.id_folha, fo.tipo_arquivo, fo.chave_folha, fo.tipo_folha_sefaz,
            phn.nome, pv.cod_institucional, doc.cpf_pessoa
        FROM ' || r.owner || '.folha_func ff
        INNER JOIN ' || r.owner || '.folha fo ON fo.id_folha = ff.id_folha AND fo.id_tipo_folha <> 1000062
        INNER JOIN ' || r.owner || '.funcionario f ON f.id_funcionario = ff.id_funcionario
        INNER JOIN ' || r.owner || '.pessoa_vinculo pv ON pv.id_pessoa_vinculo = f.id_pessoa_vinculo
        INNER JOIN sw_publico.pessoa p ON p.id_pessoa = pv.id_pessoa
        INNER JOIN sw_publico.pessoa_historico_nomes phn ON phn.id_pessoa = p.id_pessoa AND phn.data_fim IS NULL
        LEFT  JOIN sw_publico.pessoa_doc_cpf doc ON doc.id_pessoa = p.id_pessoa -- Adicionado aqui
          WHERE fo.ano = ' || p_ano || ' AND fo.mes = ' || p_mes || '
          AND NOT EXISTS (
              SELECT 1
              FROM ' || r.owner || '.folha_func ff_old
              INNER JOIN ' || r.owner || '.folha fo_old ON fo_old.id_folha = ff_old.id_folha
                    AND fo_old.id_tipo_folha <> 1000062
              INNER JOIN ' || r.owner || '.funcionario f_old ON f_old.id_funcionario = ff_old.id_funcionario
              INNER JOIN ' || r.owner || '.pessoa_vinculo pv_old ON pv_old.id_pessoa_vinculo = f_old.id_pessoa_vinculo
              WHERE pv_old.id_pessoa_vinculo = pv.id_pessoa_vinculo
                AND (fo_old.ano * 100 + fo_old.mes) < (fo.ano * 100 + fo.mes)
          )';

        EXECUTE IMMEDIATE v_sql;
    END LOOP;

    COMMIT;
END;
;
