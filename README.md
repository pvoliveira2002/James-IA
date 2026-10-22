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
- Estruturas SQLite preparadas para lembretes, loja e pedidos futuros.

Digite `ajuda` no chat para consultar os comandos.

## Ollama opcional

Instale o Ollama separadamente, obtenha um modelo pequeno (`ollama pull qwen2.5:0.5b`), inicie o serviço e selecione `ollama` na aba **CONFIG**. O James informa claramente se o serviço não estiver disponível. Nenhum conteúdo é enviado à nuvem pelo MVP.

## Segurança

As ferramentas possuem permissões em `data/settings.json`. Pesquisa e organização só acessam pastas adicionadas explicitamente na aba **CONFIG**. Alterações de arquivos exigem prévia e confirmação. Não existe terminal arbitrário, exclusão em massa, elevação administrativa nem execução direta de texto gerado pela IA. Não coloque chaves no código ou no arquivo de configuração.

## Limitações conhecidas

- Voz, impressão, pedidos e gestão completa da loja pertencem às próximas fases.
- Lembretes têm estrutura de banco preparada, mas o agendador visual ainda não integra este MVP.
- O Ollama exige instalação externa e pode ser lento neste hardware; o modo básico é o recomendado.
- A abertura dos aplicativos e o comportamento visual precisam de validação manual no Windows do usuário.
- A integração OpenAI não está habilitada nesta fase, evitando configuração acidental com custo.
- A organização move arquivos; ela não apaga nenhum conteúdo e não desfaz automaticamente a operação.

## Estrutura

`core/` interpreta solicitações; `interface/` contém a GUI; `memory/` persiste dados; `tools/` oferece ações controladas; `security/` valida permissões; `ai/` contém provedores; `modules/` reserva as áreas pessoal e loja; `tests/` cobre os módulos centrais.
