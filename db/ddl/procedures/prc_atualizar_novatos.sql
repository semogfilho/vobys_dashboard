
  CREATE OR REPLACE EDITIONABLE PROCEDURE "JOSEGOMES"."PRC_ATUALIZAR_NOVATOS" (p_schema IN VARCHAR2) AS
    v_sql VARCHAR2(4000);
BEGIN
    -- O TRUNCATE é global, então mantemos fixo
    EXECUTE IMMEDIATE 'TRUNCATE TABLE AUDITORIA_NOVATOS';

    -- Montamos o SQL dinamicamente concatenando o schema recebido
    v_sql := 'INSERT INTO AUDITORIA_NOVATOS (id_pessoa_funcionario, cod_institucional, competencia_descoberta) ' ||
             'SELECT DISTINCT ff.id_pessoa_funcionario, ff.cod_institucional, f.mes || ''/'' || f.ano ' ||
             'FROM ' || p_schema || '.folha_func ff ' ||
             'JOIN ' || p_schema || '.folha f ON f.id_folha = ff.id_folha ' ||
             'WHERE NOT EXISTS (' ||
             '    SELECT 1 FROM ALL_FOLHA_FUNC_HISTORICO hg ' ||
             '    WHERE hg.id_pessoa_funcionario = ff.id_pessoa_funcionario ' ||
             '    AND hg.cod_institucional = ff.cod_institucional ' ||
             '    AND (hg.ano < f.ano OR (hg.ano = f.ano AND hg.mes < f.mes))' ||
             ')';

    EXECUTE IMMEDIATE v_sql;
    COMMIT;
END;
;
