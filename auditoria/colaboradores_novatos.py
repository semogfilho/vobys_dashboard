# auditoria/colaboradores_novatos.py
import pandas as pd

def executar_auditoria_novatos(conn, ano, mes):
    cursor = conn.cursor()
    # Executa a procedure de carga no banco
    cursor.execute(f"BEGIN PRC_CARREGA_NOVOS_FUNC({ano}, {mes}); END;")
    cursor.close()
    
    # Query consolidada com CPF e Descrição do Tipo de Folha
    query = f"""
    SELECT 
        g.ORGAO,
        g.CHAVE_FOLHA,
        g.CPF,
        g.NOME_ATUAL,
        g.COD_INSTITUCIONAL,
        CASE g.tipo_folha_sefaz
            WHEN 'C1'  THEN '1-Padrão'
            WHEN 'C2'  THEN '2-Reintegrados'
            WHEN 'C3'  THEN '3-Temporário'
            WHEN 'C4'  THEN '4-Prestador'
            WHEN 'C5'  THEN '5-Serviços de Terceiros-Pessoas Físicas'
            WHEN 'C6'  THEN '6-Inativos'
            WHEN 'C7'  THEN '7-Pensionistas'
            WHEN 'C8'  THEN '8-Obrigações Patronais - RGPS'
            WHEN 'C9'  THEN '9-Obrigações Patronais – RPPS'
            WHEN 'C31' THEN '31 - Premiação IDEB'
            WHEN 'C35' THEN '35-Consultores PPF'
            ELSE 'Não Identificado (' || g.tipo_folha_sefaz || ')'
        END AS DESC_TIPO_FOLHA
    FROM GTT_NOVOS_FUNCIONARIOS g where TRIM(ORGAO) != 'FUNPREV'
    ORDER BY g.ORGAO, g.CHAVE_FOLHA, g.NOME_ATUAL
    """
    
    df = pd.read_sql(query, conn)
    return df

