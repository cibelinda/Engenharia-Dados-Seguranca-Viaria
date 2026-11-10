-- Dimensão de causa do acidente. Granularidade: uma linha por causa COMO A PRF ESCREVEU
-- (id_causa da origem), que é o que o fato aponta. São 101 descrições, mas várias são a mesma
-- causa escrita de outro jeito: só maiúscula ('Ultrapassagem Indevida' e 'Ultrapassagem
-- indevida'), ou a frase do BR-Brasil e a do BAT ('Dormindo' e 'Condutor Dormindo'). Por isso:
--   * `causa`: a causa harmonizada, para agrupar (as variantes ficam com o mesmo valor);
--   * `grupo`: quem ou o que causou (Condutor, Pedestre, Veículo, Via, Ambiente, Outras).
-- Uma descrição nova da PRF entra com `causa` = a própria descrição e `grupo` = 'Não
-- classificada'; o teste trecho_causa_sem_grupo avisa para classificá-la aqui.
with causa as (
    select
        id_causa,
        descricao,
        case descricao
            when 'Agressão Externa'                    then 'Agressão externa'
            when 'Animais na Pista'                    then 'Animais na pista'
            when 'Dormindo'                            then 'Condutor dormindo'
            when 'Condutor Dormindo'                   then 'Condutor dormindo'
            when 'Defeito mecânico em veículo'         then 'Defeito mecânico no veículo'
            when 'Defeito Mecânico no Veículo'         then 'Defeito mecânico no veículo'
            when 'Defeito na Via'                      then 'Defeito na via'
            when 'Falta de atenção'                    then 'Falta de atenção à condução'
            when 'Falta de Atenção à Condução'         then 'Falta de atenção à condução'
            when 'Falta de Atenção do Pedestre'        then 'Falta de atenção do pedestre'
            when 'Fenômenos da Natureza'               then 'Fenômenos da natureza'
            when 'Demais Fenômenos da natureza'        then 'Fenômenos da natureza'
            when 'Ingestão de álcool'                  then 'Ingestão de álcool pelo condutor'
            when 'Ingestão de Álcool'                  then 'Ingestão de álcool pelo condutor'
            when 'Ingestão de Substâncias Psicoativas' then 'Ingestão de substâncias psicoativas pelo condutor'
            when 'Ingestão de álcool e/ou substâncias psicoativas pelo pedestre'
                                                       then 'Ingestão de álcool ou de substâncias psicoativas pelo pedestre'
            when 'Pedestre - Ingestão de álcool/ substâncias psicoativas'
                                                       then 'Ingestão de álcool ou de substâncias psicoativas pelo pedestre'
            when 'Mal Súbito'                          then 'Mal súbito do condutor'
            when 'Condutor deixou de manter distância do veículo da frente'
                                                       then 'Não guardar distância de segurança'
            when 'Pista Escorregadia'                  then 'Pista escorregadia'
            when 'Restrição de Visibilidade'           then 'Restrição de visibilidade'
            when 'Transitar no Acostamento'            then 'Transitar no acostamento'
            when 'Ultrapassagem Indevida'              then 'Ultrapassagem indevida'
            when 'Velocidade Incompatível'             then 'Velocidade incompatível'
            when 'Obstrução Via tentativa Assalto'     then 'Obstrução da via em tentativa de assalto'
            when 'Transtornos Mentais (exceto suicidio)' then 'Transtornos mentais (exceto suicídio)'
            else descricao
        end as causa
    from {{ ref('stg_causa') }}
)

select
    id_causa,
    descricao,
    causa,
    case
        when causa in (
            'Acessar a via sem observar a presença dos outros veículos',
            'Ausência de reação do condutor',
            'Condutor desrespeitou a iluminação vermelha do semáforo',
            'Condutor dormindo',
            'Condutor não acionou o farol baixo durante o dia em rodovias de pista simples',
            'Condutor usando celular',
            'Conversão proibida',
            'Deixar de acionar o farol da motocicleta (ou similar)',
            'Desobediência à sinalização',
            'Desobediência às normas de trânsito pelo condutor',
            'Desrespeitar a preferência no cruzamento',
            'Estacionar ou parar em local proibido',
            'Falta de atenção à condução',
            'Frear bruscamente',
            'Ingestão de álcool pelo condutor',
            'Ingestão de substâncias psicoativas pelo condutor',
            'Mal súbito do condutor',
            'Manobra de mudança de faixa',
            'Não guardar distância de segurança',
            'Participar de racha',
            'Reação tardia ou ineficiente do condutor',
            'Retorno proibido',
            'Trafegar com motocicleta (ou similar) entre as faixas',
            'Transitar na calçada',
            'Transitar na contramão',
            'Transitar no acostamento',
            'Ultrapassagem indevida',
            'Velocidade incompatível'
        ) then 'Condutor'
        when causa in (
            'Desobediência às normas de trânsito pelo pedestre',
            'Entrada inopinada do pedestre',
            'Falta de atenção do pedestre',
            'Ingestão de álcool ou de substâncias psicoativas pelo pedestre',
            'Pedestre andava na pista',
            'Pedestre cruzava a pista fora da faixa'
        ) then 'Pedestre'
        when causa in (
            'Avarias e/ou desgaste excessivo no pneu',
            'Carga excessiva e/ou mal acondicionada',
            'Defeito mecânico no veículo',
            'Deficiência ou não Acionamento do Sistema de Iluminação/Sinalização do Veículo',
            'Demais falhas mecânicas ou elétricas',
            'Faróis desregulados',
            'Modificação proibida',
            'Problema com o freio',
            'Problema na suspensão'
        ) then 'Veículo'
        when causa in (
            'Acesso irregular',
            'Acostamento em desnível',
            'Acumulo de água sobre o pavimento',
            'Acumulo de areia ou detritos sobre o pavimento',
            'Acumulo de óleo sobre o pavimento',
            'Afundamento ou ondulação no pavimento',
            'Área urbana sem a presença de local apropriado para a travessia de pedestres',
            'Ausência de sinalização',
            'Curva acentuada',
            'Declive acentuado',
            'Defeito na via',
            'Deficiência do Sistema de Iluminação/Sinalização',
            'Demais falhas na via',
            'Desvio temporário',
            'Faixas de trânsito com largura insuficiente',
            'Falta de acostamento',
            'Falta de elemento de contenção que evite a saída do leito carroçável',
            'Iluminação deficiente',
            'Objeto estático sobre o leito carroçável',
            'Obras na pista',
            'Obstrução na via',
            'Pista em desnível',
            'Pista esburacada',
            'Pista escorregadia',
            'Redutor de velocidade em desacordo',
            'Restrição de visibilidade',
            'Restrição de visibilidade em curvas horizontais',
            'Restrição de visibilidade em curvas verticais',
            'Semáforo com defeito',
            'Sinalização da via insuficiente ou inadequada',
            'Sinalização encoberta',
            'Sinalização mal posicionada',
            'Sistema de drenagem ineficiente'
        ) then 'Via'
        when causa in (
            'Animais na pista',
            'Chuva',
            'Fenômenos da natureza',
            'Fumaça',
            'Neblina'
        ) then 'Ambiente'
        when causa in (
            'Agressão externa',
            'Obstrução da via em tentativa de assalto',
            'Outras',
            'Suicídio (presumido)',
            'Transtornos mentais (exceto suicídio)'
        ) then 'Outras'
        else 'Não classificada'
    end as grupo
from causa
