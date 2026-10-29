# James IA — Fase 1

Assistente pessoal e de loja para Windows, leve, local e supervisionado. O MVP funciona sem internet, conta ou API paga.

## Histórico resumido de atualizações

Os registros abaixo são permanentes. Cada nova entrega deve ser adicionada como uma nova entrada, sem apagar ou substituir as anteriores.

### 22/10/2026 — Implementação da Fase 1

Foi concluído o MVP da Fase 1 do James IA: interface gráfica, chat, histórico SQLite, tarefas, memórias, comandos do Windows e organização segura de arquivos. Também foram adicionados diretórios autorizados, permissões configuráveis e integração opcional com Ollama. A implementação passou em 10 testes automatizados e no teste de inicialização da interface.

### 22/10/2026 — Correção do organizador de arquivos

O organizador ganhou uma janela própria que mostra nome, extensão, tamanho, origem, categoria e destino de cada arquivo. A análise agora ocorre em segundo plano e nunca move arquivos; a movimentação só é liberada após pré-visualização e confirmação. Também foram adicionadas autorização explícita de pastas, opção separada para subpastas, novas categorias e proteção contra nomes duplicados e sobrescrita.

### 22/10/2026 — Fase 1.5: cérebro conversacional

O James passou a encaminhar conversas naturais para Ollama ou OpenAI sem perder os comandos locais. Foram adicionados contexto recente limitado, privacidade configurável das memórias, status do provedor e solicitações estruturadas de ferramentas com confirmação obrigatória. A OpenAI usa a Responses API, lê a chave somente de `OPENAI_API_KEY` e pode gerar custos. A entrega foi validada com 23 testes automatizados e teste de inicialização da interface.

### 22/10/2026 — Instalação do SDK OpenAI

O SDK OpenAI 3.36.1 foi instalado no perfil do usuário para habilitar o provedor de nuvem do James. A chave não foi gravada porque o valor fornecido era apenas um exemplo; ainda é necessário configurar uma chave real em `OPENAI_API_KEY`. Após a instalação, os 23 testes automatizados continuaram aprovados.

### 22/10/2026 — Instalação do Ollama local

O Ollama 0.40.8 foi instalado no Windows e o modelo `qwen2.5:0.5b` de 397,8 MB foi baixado. A API local em `127.0.0.1:11434` e uma conversa real em português foram testadas com sucesso. O James agora pode usar conversação local sem cobrança de API.

### 22/10/2026 — Dashboard futurista do James IA

A interface principal foi reconstruída em Tkinter com base na referência: menu lateral, barra superior, núcleo holográfico, atividade recente, ações rápidas, monitor real de CPU/RAM/disco, conversas recentes, provedor ativo, memória e barra de comunicação. Tarefas, memórias, conversas, arquivos e configurações continuam funcionais; módulos futuros aparecem como “Em desenvolvimento”. Foi criado um backup anterior em `backups/2026-10-22_pre_dashboard`, uma captura real em `data/dashboard_capture.png` e a entrega passou em 26 testes automatizados.

### 22/10/2026 — Gerenciador universal de aplicativos

O James ganhou descoberta de aplicativos pelo Menu Iniciar, App Paths, Get-StartApps, AppUserModelID e PATH, com cache SQLite e atualização assíncrona. A tela “Aplicativos do Windows” permite pesquisar, abrir, atualizar, cadastrar portáteis, criar apelidos, definir permissões, favoritos e consultar o histórico. A abertura usa somente IDs catalogados, confirmação e `shell=False`, bloqueando scripts e comandos arbitrários. Foram indexados 258 aplicativos em 0,87 segundo e 37 testes passaram. Calculadora, Bloco de Notas, Paint, Brave e Ferramenta de Captura foram abertos e verificados; o atalho web do Bling apresentou erro de carregamento e o Excel 2007 encerrou sem janela.

### 22/10/2026 — Navegação inteligente e tarefas web

O James ganhou navegação supervisionada com Playwright usando o Google Chrome instalado e um perfil exclusivo em `data/browser_profile`, sem reutilizar cookies pessoais. Foram adicionados catálogo seguro de sites, busca real no YouTube, escolha contextual de resultados, retorno à página anterior, pesquisa no Google, plano limitado, interrupção, verificação e histórico SQLite. A nova tela “Automações” mostra etapas, estados e erros; URLs locais, privadas, `file:` e `javascript:` permanecem bloqueadas. O backup anterior está em `backups/2026-10-22_pre_browser_automation`.

Validação final: a busca real por “como fazer canecas sublimadas” retornou cinco vídeos, o segundo resultado foi aberto e o retorno à lista funcionou. A interface iniciou na nova tela e todos os 42 testes automatizados foram aprovados.

### 22/10/2026 — Correção do WhatsApp Web

O WhatsApp Web passou a reconhecer quatro formas naturais de solicitação e agora abre `https://web.whatsapp.com/` no navegador padrão do Windows, preservando a sessão habitual sem copiar cookies. Aberturas simples de Google e YouTube também usam o navegador padrão; o Playwright continua reservado às automações que precisam ler e operar a página. Foram adicionados diagnóstico de comando, URL, navegador, resultado e exceções, proteção contra abas duplicadas em sequência e mensagem honesta quando o carregamento não pode ser verificado. A validação real foi aceita pelo navegador `WindowsDefault`, a repetição do WhatsApp não criou outra aba e os 45 testes passaram. Backup: `backups/2026-10-22_pre_whatsapp_web_fix`.

### 22/10/2026 — Aplicativos modernos e WhatsApp Desktop

O catálogo agora separa programas Windows de PWAs do Chrome/Edge: “abra o WhatsApp” procura somente o aplicativo instalado, enquanto “WhatsApp Web” continua no navegador. A busca aproximada foi endurecida para não sugerir programas sem relação, nomes exatos ganharam prioridade e o lançador diferencia processo verificado de mera solicitação enviada. O computador foi inspecionado com `Get-StartApps`, Appx, registros, Menu Iniciar e locais oficiais: existe apenas o PWA WhatsApp Web, não o WhatsApp Desktop, portanto o James agora informa corretamente que o programa não está instalado. O caminho `shell:AppsFolder\AppUserModelID` foi testado e a Calculadora UWP abriu com processo real confirmado; 50 testes passaram. Backup: `backups/2026-10-22_pre_whatsapp_desktop_fix`.

### 22/10/2026 — Navegação inteligente completa

A navegação foi dividida entre modo simples com o navegador padrão e modo inteligente sob demanda com Playwright. O James ganhou contexto próprio de navegação (site, objetivo, consulta, resultados, histórico, etapa, status e erro), pesquisa real no Google e YouTube, seleção por posição ou título, retorno aos resultados, leitura de texto público, localização de contatos, pesquisa restrita ao site oficial da Epson e capturas em `data/browser_diagnostics`. A tela “NAVEGAÇÃO INTELIGENTE” exibe o estado da tarefa e oferece Voltar, Interromper e atalhos, sem bloquear a interface. Na validação real, o YouTube retornou três vídeos, abriu o segundo e voltou; o Google retornou cinco resultados públicos. Todos os 55 testes passaram. Backup: `backups/2026-10-22_pre_smart_navigation`.

Limitações desta etapa: Google e YouTube podem mudar o HTML ou solicitar CAPTCHA; o James informa o bloqueio e não o contorna. Links do Google podem ser apresentados pelo redirecionador seguro do próprio Google. Resumos de páginas dependem do texto publicamente visível, e ações como login, mensagens, formulários, compras, pagamentos, uploads e downloads continuam fora da execução automática e exigem confirmação/implementação específica.

### 22/10/2026 — Correção de comandos compostos do YouTube

O interpretador agora analisa a frase completa antes dos atalhos e separa três intenções: abrir o YouTube, pesquisar vídeos e pesquisar mais abrir um vídeo relevante. Expressões como “abra no YouTube um tutorial”, “quero assistir uma aula”, “me mostra um vídeo” e o erro “tutoria” são reconhecidos; a pesquisa usa `urlencode`, mantém resultados reais no contexto e aceita “coloca o segundo”, “procure outro” e “mais recente”. Se o Playwright falhar, a URL direta de resultados é aberta sem inventar vídeo. No teste real, “abra no YouTube um tutorial de blusa personalizada” abriu e confirmou uma URL `/watch` do vídeo “COMO CRIAR ESTAMPAS QUE VENDEM USANDO A KITTL | PASSO A PASSO”. Todos os 59 testes passaram. Backup: `backups/2026-10-22_pre_compound_youtube_fix`.

### 22/10/2026 — Central de Comando com conversa e relatórios

A tela inicial passou a ser o centro real de interação: exibe a conversa ativa em tempo real, mantém o campo global de envio, mostra atividades e relatórios recentes com botão “Ver” e oferece expansão para o histórico completo. A antiga seção “Conversas” foi renomeada para “Histórico de Conversas” e a nova seção “Relatórios” consulta resultados, etapas e erros anteriores diretamente das tabelas SQLite existentes, sem duplicar mensagens. O núcleo holográfico, monitor e identidade visual foram preservados; a área já indica preparação para microfone e voz futuros. A captura validada está em `data/command_center_capture.png`, a montagem da tela permaneceu abaixo do limite de desempenho e todos os 63 testes passaram. Backup: `backups/2026-10-22_pre_command_center_chat`.

### 22/10/2026 — Interface profissional 2.0

A Central de Comando foi reorganizada com o chat em destaque, balões separados para usuário e James, menu lateral agrupado e recolhível, painel único de atividades/resultados também recolhível, ações rápidas compactas e monitor real no rodapé. O histórico SQLite, as automações, permissões e demais telas foram preservados; relatórios só abrem arquivos por ação do usuário e dentro de caminhos autorizados. A interface foi validada em 1920×1080, 1600×900 e 1366×768, consumiu cerca de 47 MB em repouso e os 66 testes passaram. Capturas: `data/interface_2_capture.png` e `data/interface_2_1366x768.png`. Backup: `backups/2026-10-22_pre_interface_2`.

### 22/10/2026 — Preparação do repositório Git

O projeto foi preparado para versionamento no Git com código, testes, documentação e capturas da interface. Bancos SQLite, configurações locais, logs, ambientes virtuais, backups e o perfil privado do navegador foram excluídos pelo `.gitignore`, evitando publicar sessões, cookies ou dados pessoais da máquina.

### 23/10/2026 — Publicação no GitHub

O projeto foi publicado no repositório `pvoliveira2002/James-IA`, usando a branch principal `main`. O repositório local ficou vinculado ao remoto `origin`, permitindo que as próximas atualizações sejam enviadas sem uma nova configuração.

### 24/10/2026 — Módulo de voz local

O botão de microfone da Central de Comando passou a iniciar e parar uma captura sob demanda com Vosk e `sounddevice`, sem escuta contínua nem armazenamento de áudio. A transcrição usa o mesmo fluxo do chat e a leitura opcional das respostas utiliza SAPI5 por meio do `pyttsx3`. Captura, reconhecimento e síntese trabalham fora da thread gráfica, com estados Ouvindo, Processando, Pronto e Erro. As dependências e o modelo são opcionais e não são baixados automaticamente. Backup: `backups/2026-10-24_pre_voice_module`.

### 24/10/2026 — Instalação local da voz

Foram instalados Vosk 0.3.45, `sounddevice` 0.5.6 e `pyttsx3` 2.99. O modelo brasileiro `vosk-model-small-pt-0.3` foi baixado da fonte oficial, extraído em `data/models` e configurado com a entrada de voz ativa. O James também passou a localizar automaticamente um microfone quando o Windows não define uma entrada padrão e a negociar a frequência suportada pelo dispositivo.

### 24/10/2026 — Agendador inteligente

O James ganhou agenda visual e comandos naturais para criar, listar, editar, concluir, adiar e excluir lembretes. Datas relativas, amanhã, horários e repetições diárias ou semanais são interpretados localmente pelo mesmo fluxo usado no texto e na voz. Um serviço leve verifica vencimentos em segundo plano, evita notificações duplicadas e usa notificações nativas do Windows com botões para adiar ou concluir. Os lembretes existentes são migrados e preservados no SQLite. Backup: `backups/2026-10-24_pre_smart_scheduler`.

Validação: a notificação nativa foi solicitada com sucesso no Windows e todos os 84 testes automatizados foram aprovados.

### 26/10/2026 — Correção de abertura do ChatGPT e confirmações

O James agora diferencia ChatGPT Desktop, site e conversa antes de executar. As formas “ChatGPT” e “Chat GPT” usam o mesmo destino: o catálogo do Windows é atualizado, um aplicativo nativo encontrado exige confirmação e, quando ele não existe, o James oferece `https://chatgpt.com/` no navegador padrão. O matching aproximado passou a rejeitar sugestões sem relação, como Character Map, e respostas isoladas como “abrir”, “sim” ou “confirmar” só atuam quando existe um destino válido pendente. As mensagens distinguem solicitação enviada, processo verificado e falha. O computador possui apenas um PWA do ChatGPT no Chrome, não o aplicativo Desktop nativo; por isso o comportamento local correto é oferecer o site. Todos os 89 testes foram aprovados. Backup: `backups/2026-10-26_pre_chatgpt_routing`.

### 26/10/2026 — Interface JAMES/NEXUS 3.0

A Central de Comando recebeu a identidade NEXUS 3.0 em azul-preto, com painéis holográficos, atalhos funcionais, chat persistente e campo de texto permanente. O núcleo 2.5D usa apenas Canvas reutilizável, partículas e órbitas leves: ciano indica pronto, azul processamento, verde somente conclusão verificada, vermelho erro real e âmbar confirmação pendente. Solicitações de abertura que não permitem verificar o carregamento permanecem ciano e nunca simulam sucesso. A animação trabalha perto de 18 FPS quando ativa e reduz a frequência em repouso ou sem visibilidade. Os layouts 1366×768 e 1920×1080 foram validados, a captura local está em `data/nexus_3_1366x768.png` e todos os 92 testes passaram. Backup: `backups/2026-10-26_pre_nexus_3`.

### 26/10/2026 — Inteligência conversacional evoluída

O James passou a manter melhor a continuidade entre perguntas, resolver referências aos turnos recentes e reconhecer mudanças de assunto sem misturar temas. As respostas de Ollama e OpenAI agora podem aparecer progressivamente na interface sem bloquear o Tkinter nem duplicar o histórico SQLite; o contexto recente continua temporário e somente pedidos explícitos criam memória persistente. O seletor lista modelos Ollama instalados e oferece `qwen3:1.7b` sem substituir automaticamente o `qwen2.5:0.5b` configurado. O `qwen3:1.7b` foi instalado e respondeu localmente por streaming em 5,81 segundos neste computador, enquanto a OpenAI permaneceu sem chamada paga. Todos os 102 testes automatizados passaram. Backup: `backups/2026-10-26_pre_conversation_2`.

### 26/10/2026 — NEXUS 3.1: memória contextual e ações confiáveis

O NEXUS 3.1 reutiliza os módulos existentes e acrescenta recuperação lexical leve das memórias autorizadas, ensinamentos pelo chat, correção por número, proteção contra duplicação e exclusão confirmada. Respostas de ação agora carregam estados explícitos — solicitada, executada, verificada, confirmação ou erro — e o núcleo mantém aberturas não verificadas em ciano, sem declarar sucesso. O chat ganhou etiquetas e botões contextuais funcionais para continuar, escolher, abrir, excluir ou cancelar, preservando permissões e confirmações. Nenhum modelo foi trocado ou baixado automaticamente, nenhuma dependência pesada foi adicionada e todos os 109 testes passaram. Backup: `backups/2026-10-26_pre_nexus_3_1`.

### 26/10/2026 — Correção das perguntas sobre capacidades

Perguntas como “Quais serviços eu posso pedir pra você, James?”, “O que você sabe fazer?” e “Como pode me ajudar?” agora são resolvidas localmente, sem depender do modelo de IA. A resposta é gerada a partir das ferramentas, permissões e provedor realmente disponíveis, separando recursos ativos, desativados e ainda não implementados. O histórico ganhou escopo por conversa, migração preservando as 124 mensagens existentes, ordem cronológica e remoção de duplicações consecutivas no contexto. O Ollama recebeu instruções mais diretas contra saudações vazias e repetição, e os diagnósticos registram intenção, provedor e tipo de falha sem gravar o texto pessoal. Todos os 117 testes passaram. Backup: `backups/2026-10-26_pre_capabilities_fix`.

## Instalação no Windows

1. Instale o Python 3.11 ou mais recente pelo site oficial e marque **Add Python to PATH**.
2. Abra esta pasta e dê dois cliques em `iniciar_jarvis.bat`.

O banco `data/james.db` e as configurações são criados automaticamente. Para usar somente o modo Básico ou Ollama, não há dependências Python externas. Para usar OpenAI, instale:

```powershell
python -m pip install -r requirements.txt
setx OPENAI_API_KEY "sua-chave-aqui"
```

Feche e abra o James após configurar a variável. A API da OpenAI é opcional e pode gerar custos conforme o modelo e o uso.

Para executar pelo terminal:

```powershell
python main.py
```

Para executar os testes:

```powershell
python -m unittest discover -v
```

## Funcionalidades implementadas

- Interface Tkinter responsiva, tema grafite, verde e azul.
- Central de Comando JAMES/NEXUS 3.0 com núcleo holográfico reativo e animação leve.
- Chat com histórico persistente em SQLite e processamento em segundo plano.
- Modo básico offline com comandos determinísticos.
- Abertura autorizada de Calculadora, Bloco de Notas e navegador.
- Abertura por nome de pastas previamente autorizadas e painel de permissões configurável.
- Informações básicas do computador.
- Cadastro, consulta, conclusão e exclusão confirmada de tarefas.
- Cadastro, consulta, edição e exclusão confirmada de memórias.
- Pesquisa de arquivos apenas em pastas autorizadas.
- Organização por tipo com prévia, confirmação e tratamento de nomes repetidos.
- Registro de ações de ferramentas no banco.
- Provedor Ollama opcional e modelo configurável (padrão `qwen2.5:0.5b`).
- Conversação natural com contexto recente via Ollama ou OpenAI Responses API.
- Provedor OpenAI opcional, modelo configurável e chave lida do ambiente.
- Ferramentas estruturadas solicitadas pela IA, sempre sujeitas a confirmação.
- Entrada de voz local sob demanda com Vosk e respostas faladas opcionais pelo SAPI5.
- Agenda local com lembretes únicos ou recorrentes, filtros visuais e notificações do Windows.
- Estruturas SQLite preparadas para loja e pedidos futuros.

Digite `ajuda` no chat para consultar os comandos.

## Voz opcional

1. Instale as dependências sem alterar o funcionamento do modo de texto:

```powershell
python -m pip install -r requirements-voice.txt
```

2. Baixe manualmente o modelo leve brasileiro `vosk-model-small-pt-0.3` na [página oficial de modelos do Vosk](https://alphacephei.com/vosk/models) e extraia-o em uma pasta local. O James não baixa modelos automaticamente.
3. Abra **Configurações**, marque **Ativar entrada por microfone**, selecione a pasta extraída do modelo e salve. Marque **Falar respostas do James** se também desejar a saída por voz.
4. Pressione o botão 🎙 para começar, fale e pressione novamente para parar e processar. A tecla `Esc` cancela uma captura em andamento.

O áudio existe apenas na memória durante a captura e não é salvo. Sem as dependências ou sem um modelo configurado, o chat de texto continua funcionando normalmente.

## Agenda e lembretes

A seção **Agenda** oferece os filtros Hoje, Próximos, Recorrentes e Concluídos. Exemplos aceitos no chat e pelo microfone:

- `Me lembre de pagar a conta amanhã às 14h.`
- `Crie um lembrete para conferir a prensa daqui a 30 minutos.`
- `Agende um lembrete para tomar remédio todos os dias às 8h.`
- `Mostre meus lembretes.`
- `Adie o lembrete 2 por 30 minutos.`
- `Conclua o lembrete 2.`
- `Exclua o lembrete 2.`

Exclusões sempre pedem confirmação. Datas sem dia ou horário suficiente geram uma pergunta de esclarecimento. O pacote leve `windows-toasts`, instalado por `requirements.txt`, fornece as notificações nativas.

## Ollama opcional

Instale o Ollama separadamente, obtenha um modelo pequeno (`ollama pull qwen2.5:0.5b`), inicie o serviço e selecione `ollama` na aba **CONFIG**. O James informa claramente se o serviço não estiver disponível. Nenhum conteúdo é enviado à nuvem pelo MVP.

O modelo `qwen3:1.7b` também pode ser instalado com `ollama pull qwen3:1.7b`. Depois, use **Atualizar modelos Ollama** e selecione-o manualmente nas Configurações; instalar ou testar um modelo nunca altera sozinho o modelo ativo. Para preservar desempenho no i3 com 8 GB, o contexto local é limitado e as respostas usam streaming em uma thread de trabalho.

## Segurança

As ferramentas possuem permissões em `data/settings.json`. Pesquisa e organização só acessam pastas adicionadas explicitamente na aba **CONFIG**. Alterações de arquivos exigem prévia e confirmação. Não existe terminal arbitrário, exclusão em massa, elevação administrativa nem execução direta de texto gerado pela IA. Não coloque chaves no código ou no arquivo de configuração.

## Limitações conhecidas

- Impressão, pedidos e gestão completa da loja pertencem às próximas fases.
- A precisão da voz depende do microfone e do modelo Vosk escolhido; o modelo pequeno prioriza baixo consumo de memória.
- O agendador verifica lembretes enquanto o James está aberto; lembretes vencidos durante o fechamento são recuperados na próxima inicialização.
- Os botões Adiar e Concluir das notificações precisam que o James continue aberto para processar a ação.
- O Ollama exige instalação externa e pode ser lento neste hardware; o modo básico é o recomendado.
- A abertura dos aplicativos e o comportamento visual precisam de validação manual no Windows do usuário.
- A integração OpenAI não está habilitada nesta fase, evitando configuração acidental com custo.
- A organização move arquivos; ela não apaga nenhum conteúdo e não desfaz automaticamente a operação.

## Estrutura

`core/` interpreta solicitações; `interface/` contém a GUI; `memory/` persiste dados; `tools/` oferece ações controladas; `security/` valida permissões; `ai/` contém provedores; `modules/` reserva as áreas pessoal e loja; `tests/` cobre os módulos centrais.
