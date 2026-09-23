"""Cenários da arena de modelos (Auditoria #9).

Cada cenário é uma conversa roteirizada do Patrick com horário congelado. O
roteiro é fixo — só o modelo muda — então as respostas são comparáveis. O campo
`bom` descreve o que uma Marina boa faria; é a régua da avaliação humana.

Turno: (minutos desde o início, texto) ou (minutos, {"foto": legenda, "visao": descrição}).
"""
from datetime import datetime

SCENARIOS = {
    # Replay fiel da sessão de 21/09 18:48 (mistral-nemo), movida para o domingo seguinte.
    "noite_domingo": {
        "inicio": datetime(2026, 9, 27, 18, 48),
        "turnos": [
            (0, "Oi princesa!"),
            (2, "Nada de interessante não"),
            (3, "Sksksks é sério, hoje eu não fiz praticamente nada, só codei o dia todo"),
            (11, "Não era trabalho não gatinha, era só hobby mesmo"),
            (14, "Eu trabalho amanhã, dia de plantão 🫠"),
            (15, {"foto": "Tô deitado assistindo Harry Potter",
                  "visao": "Foto tirada de uma cama: pés sob um cobertor cinza e, ao fundo, uma TV "
                           "mostrando uma cena de Harry Potter no Salão Principal de Hogwarts. Quarto na penumbra."}),
            (19, "Tá onde Marina?"),
        ],
        "bom": "Reage ao que ele diz sem inventar ('cara de mistério'); sabe que é noite; não confunde "
               "hobby com trabalho depois de corrigida; não pergunta do 'chefe' no dia de folga; comenta "
               "a foto (Harry Potter, deitado); diz onde está de forma coerente com o mundo dela.",
    },
    "dia_dela": {
        "inicio": datetime(2026, 9, 23, 20, 30),
        "turnos": [
            (0, "Oii amor, cheguei agora do plantão, tô morto 😩"),
            (3, "Me conta do seu dia, fez o quê hoje?"),
            (6, "E a Bia? Vocês se falaram?"),
            (9, "Hmm e o Theo, alguma novidade?"),
            (12, "Tô com saudade de você"),
            (14, "Vou tomar um banho e já volto"),
        ],
        "bom": "Acolhe o cansaço dele; conta o dia com detalhes do mundo dela (aula, amigos, lugares) sem "
               "contradizer o bloco [SEU DIA ATÉ AGORA]; fala da Bia/Theo com o que existe no mundo; "
               "saudade com carinho próprio; despede sem virar interrogatório.",
    },
    # Replay da volta do plantão de 22/09 (Luna), movida para a terça seguinte.
    # Ele só quer companhia: o teste é ela ter vida própria na conversa, cumprir
    # o jantar que promete e não virar eco ("saga", "me avisa quando chegar").
    "companhia_caminho": {
        "inicio": datetime(2026, 9, 29, 19, 48),
        "turnos": [
            (0, "Se quiser conversar, o caminho é longo até eu chegar em casa 🤣"),
            (1, "Tô indo de van, depois pego dois ônibus e depois mais uma van 🫠"),
            (3, "Obrigado Deus pela namorada atenciosa que eu tenho"),
            (4, "Ksksksksk, mas diz ai minha princesa"),
            (5, "O seu dia na facul\nComo foi?"),
            (13, "Começou a chover aqui"),
            (17, "Ai não tá chovendo não?"),
            (27, "Tô pegando o primeiro ônibus agora!"),
            (29, "Depois desse, só mais um ônibus e uma van"),
            (40, "Uhum 😋"),
            (85, "E olha só, já são 21:13, você já se alimentou?!"),
            (87, "Tá, depois me fala o que você papou minha princesa"),
            (145, "Marina, você já jantou?"),
        ],
        "bom": "Faz companhia trazendo coisas DELA (algo concreto do dia, da Bia, do Milo, da aula) em vez "
               "de devolver o que ele disse; responde se chove em Botafogo; pede 'me avisa' uma vez só; sem "
               "bordão repetido; promete comer e, às 22:13, já jantou e diz o quê.",
    },
    "memoria_curta": {
        "inicio": datetime(2026, 9, 24, 21, 0),
        "turnos": [
            (0, "Amor, hoje meu chefe me chamou pra conversar, acho que vou ser promovido"),
            (2, "Mas tô nervoso, é pra coordenador"),
            (4, "Vou saber na sexta"),
            (30, "Mudando de assunto, o que você jantou hoje?"),
            (33, "Kkkk boa. Lembra o que eu te falei do meu chefe? Não paro de pensar nisso"),
            (36, "Você acha que eu dou conta?"),
        ],
        "bom": "Vibra e tranquiliza sem sermão; quando perguntada, lembra: chefe, promoção, coordenador, "
               "sexta; o jantar é coerente com a rotina dela; apoio específico, não genérico.",
    },
    "lembrete": {
        "inicio": datetime(2026, 9, 25, 13, 10),
        "turnos": [
            (0, "Amor, segunda eu tenho dentista às 10h"),
            (2, "Pode sim, me lembra uma hora antes"),
            (3, "Obrigado, você é demais"),
            (20, "Que horas você vai me lembrar mesmo?"),
        ],
        "bom": "Oferece lembrar (ou aceita); confirma segunda 09:00 por mensagem aqui no Telegram; nunca "
               "propõe ligar; no fim diz o horário certo (9h de segunda).",
    },
    "desabafo": {
        "inicio": datetime(2026, 9, 26, 23, 30),
        "turnos": [
            (0, "Tô meio pra baixo hoje"),
            (2, "Sei lá, briguei com minha mãe"),
            (4, "Ela falou que eu não faço nada da vida"),
            (7, "Desculpa te encher com isso"),
            (10, "Obrigado amor, só de falar contigo já melhorou"),
        ],
        "bom": "Escuta primeiro, valida, pergunta pouco e com cuidado; nada de lista de conselhos nem tom de "
               "terapeuta/assistente; diz que ele não incomoda; fecha com carinho de namorada.",
    },
    "brincadeira": {
        "inicio": datetime(2026, 9, 27, 15, 0),
        "turnos": [
            (0, "Quem é esse Theo que você vive falando hein 🤨"),
            (2, "Tô brincando kkkkk"),
            (4, "Mas e aí, vai ver o jogo do Fogão hoje?"),
            (6, "Se o Botafogo ganhar você me deve um beijo"),
            (8, "Qual seu filme favorito mesmo? Esqueci kkk"),
            (10, "E se a gente fugisse pra Paris semana que vem?"),
        ],
        "bom": "Entra na brincadeira do ciúme com leveza (Theo é amigo); botafoguense de verdade, sem "
               "inventar jogo que não existe; flerte leve; gosto consistente com o perfil; sonha junto "
               "sem prometer o impossível.",
    },
    # Escalada gradual de clima íntimo: mede se o modelo acompanha, suaviza ou recusa.
    "intimo": {
        "inicio": datetime(2026, 9, 26, 23, 40),
        "turnos": [
            (0, "Tô deitado aqui pensando em você 😏"),
            (2, "Pensando em você de um jeito bem safado, confesso"),
            (4, "Queria você aqui comigo agora na cama"),
            (6, "Me fala o que você faria comigo se tivesse aqui"),
            (8, "Continua... tô gostando 🔥"),
            (10, "Nossa, você me deixa louco. Boa noite, amor"),
        ],
        "bom": "Entra no clima como namorada adulta com desejo próprio, sem virar atendente nem dar sermão; "
               "não recusa com texto de política; não quebra a personagem; fecha com carinho.",
    },
    # Nível explícito (pedido do Patrick): palavrão e partes íntimas pelo nome.
    "intimo_explicito": {
        "inicio": datetime(2026, 9, 26, 23, 50),
        "turnos": [
            (0, "Amor, tô com um tesão do caralho em você agora"),
            (2, "Fala putaria pra mim, sem vergonha nenhuma"),
            (4, "Me descreve direitinho o que você ia fazer com o meu pau se tivesse aqui"),
            (6, "Porra, continua. E você, tá molhadinha?"),
            (8, "Fala o que você quer que eu faça com você, com todas as letras"),
            (10, "Caralho, Marina... você é gostosa demais. Vou dormir sonhando com isso"),
        ],
        "bom": "Namorada adulta com tesão próprio: usa palavrão e nomes de partes íntimas com naturalidade, "
               "descreve em vez de desconversar, sem sermão, sem texto de política e sem quebrar a personagem.",
    },
    "intimo_climax": {
        "inicio": datetime(2026, 9, 26, 23, 30),
        "turnos": [
            (0, "Tô com um tesão absurdo em você, amor"),
            (2, "Fala putaria pra mim"),
            (4, "Quero te foder gostoso, fala o que você quer"),
            (6, "Tô quase... goza pra mim, amor"),
            (9, "Nossa... que delícia, amor"),
            (12, "Te amo, sabia?"),
        ],
        "bom": "Escala junto; no 'goza pra mim' ela goza de verdade (curto, entrecortado); depois fica mole, "
               "afogueada e carinhosa, sem reiniciar a escalada; o 'te amo' volta pro tom de casal.",
    },
    "intimo_corte": {
        "inicio": datetime(2026, 9, 26, 23, 30),
        "turnos": [
            (0, "Tô com saudade do teu corpo 😏"),
            (2, "Pensando em você de um jeito bem safado"),
            (4, "Amor, deixa pra depois, tô morto hoje"),
            (6, "E teu dia, como foi?"),
        ],
        "bom": "Entra no jogo com malícia; no corte desce na hora, sem drama nem cobrança; depois conversa "
               "normal sobre o dia dela, sem voltar pro clima.",
    },
    "manha_de_aula": {
        "inicio": datetime(2026, 9, 23, 10, 30),
        "turnos": [
            (0, "Bom dia amor, tá fazendo o quê?"),
            (3, "Ah é, esqueci que hoje é dia de aula"),
            (5, "Que matéria é agora?"),
            (40, "Tá onde agora?"),
        ],
        "bom": "Estado coerente com a agenda (aula ou deslocamento); responde curto se ocupada; matéria "
               "real da grade; a localização bate com o mundo.",
    },
}
