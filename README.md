# ⚡ Robô de Candidaturas Automáticas para Vagas Internacionais (LinkedIn)

Um sistema em Python moderno, seguro e visual projetado para buscar e se candidatar automaticamente a **vagas internacionais 100% remotas** no LinkedIn através do **Easy Apply (Candidatura Simplificada)**.

Agora disponível com **Interface Web Moderna em Streamlit** e modo Linha de Comando (CLI).

---

## 🌟 Principais Recursos

1. **Interface Web Visual em Streamlit (`app.py`)**:
   - **Dashboard**: Cartões de métricas, taxa de sucesso, gráficos de área e donut Plotly.
   - **Buscar Vagas (Live Runner)**: Controle de execução em tempo real com botão Start/Stop, barra de progresso e terminal de logs com streaming.
   - **Perfil do Candidato**: Edição de competências, respostas internacionais e upload de currículo em PDF via drag-and-drop.
   - **Configurações**: Alternador do modo Dry-Run/Real, delays humanos e chaves de IA.
   - **Relatórios & Histórico**: Filtros avançados por status/empresa e exportação completa para CSV.
2. **Sessão Persistente e Segura (Playwright)**:
   - Login manual seguro realizado uma única vez com suporte a 2FA/SMS.
   - Validação automática de sessão antes de iniciar qualquer ciclo.
3. **Preenchimento Híbrido e Resiliente**:
   - Resolução determinística imediata de anos de experiência, pretensão salarial em USD, vistos e nível de inglês.
   - Suporte inteligente a checkboxes (confirmações, termos e skills).
   - Anexo automático de currículo em PDF em inglês.
   - Fallback para IA generativa (Gemini, OpenAI ou Ollama).
4. **Proteção Anti-Bloqueio & Anti-Detecção**:
   - Delays e digitação com ritmo humano.
   - Limite diário estrito (padrão: 15 vagas/dia).
   - Resiliência de rede com biblioteca `tenacity` (retry com espera exponencial).
   - Modo de Simulação (*Dry-Run*) ativado por padrão.
5. **Histórico Local em SQLite**:
   - Registro permanente em `data/applications.db` e logs em `data/bot.log`.

---

## 🚀 Como Iniciar a Interface Web (Recomendado)

### 1. Ativar o Ambiente Virtual

No terminal PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

*(Caso haja restrição de execução de scripts no PowerShell, execute `.\.venv\Scripts\streamlit.exe run app.py` diretamente).*

---

### 2. Iniciar a Aplicação Web

Execute o comando:

```powershell
.\.venv\Scripts\streamlit run app.py
```

Seu navegador padrão abrirá automaticamente no endereço:
👉 **`http://localhost:8501`**

---

## 💻 Como Usar via Linha de Comando (CLI Alternativo)

Se preferir rodar direto no terminal sem abrir o navegador:

```powershell
.\.venv\Scripts\python cli.py
```

Menu interativo:
```text
[1] Iniciar candidaturas automáticas
[2] Ver estatísticas
[3] Testar respostas do resolvedor de perguntas
[4] Alternar modo Dry-Run / Real
[5] Sair
------------------------------------
[0] Configuração de Login / Setup Session
```

---

## 🔑 Autenticação Única no LinkedIn (Setup Session)

Antes de rodar as candidaturas pela primeira vez:
1. No menu lateral da interface web, clique em **`🔑 Fazer Login 1x`**, ou execute no terminal:
   ```powershell
   .\.venv\Scripts\python setup_session.py
   ```
2. Uma janela real do Chrome será aberta.
3. Entre com sua conta do LinkedIn e resolva o 2FA/SMS.
4. Quando estiver no Feed inicial, retorne ao terminal e pressione **ENTER**.
5. Sua sessão ficará salva de forma permanente na pasta `.session/`.

---

## 🔧 Guia de Troubleshooting

- **Sessão Expirada**: Se o robô acusar que a sessão expirou, basta executar o setup de login novamente pelo botão da Sidebar ou via `python setup_session.py`.
- **CAPTCHA**: Caso o LinkedIn exiba uma verificação de segurança, abra o setup de login e resolva o desafio com o mouse no navegador real.
- **Modo Simulação (Dry-Run)**: Recomendamos sempre manter o modo Dry-Run ligado nas primeiras execuções para verificar como o robô preenche as etapas do Easy Apply na sua tela.

---

## 📂 Estrutura do Projeto

```text
vagas_automaticas/
├── app.py                   # Aplicação Web Streamlit Principal
├── cli.py                   # Painel CLI interativo para terminal
├── setup_session.py         # Script para login manual e 2FA
├── components/              # Componentes visuais da Web UI
│   ├── metrics.py           # Cards métricos estilizados
│   ├── charts.py            # Gráficos interativos Plotly
│   ├── tables.py            # Tabelas com badges coloridos e exportação CSV
│   └── forms.py             # Formulários de busca e perfil
├── utils/                   # Módulos utilitários
│   ├── logger.py            # Streaming de logs em tempo real
│   ├── config_manager.py    # Gerenciador de config.yaml e .env
│   ├── profile_manager.py   # Gerenciador do perfil e upload de currículo
│   └── session_manager.py   # Gerenciador de sessão do LinkedIn
├── core/                    # Núcleo de automação
│   ├── browser.py           # Playwright com stealth e validação de login
│   ├── search.py            # Motor de busca com filtros internacionais
│   ├── form_handler.py      # Preenchimento resiliente do Easy Apply
│   ├── ai_solver.py         # Resolução por regras e fallback para LLM
│   ├── engine.py            # Orquestrador ApplicationEngine com retries
│   └── tracker.py           # Banco SQLite de histórico
├── config/
│   ├── config.yaml          # Parâmetros de busca, limites e segurança
│   ├── profile.yaml         # Seus dados e competências
│   └── cv/resume.pdf        # Seu currículo em PDF em inglês
├── data/
│   ├── applications.db      # Banco de dados SQLite
│   └── bot.log              # Logs com timestamps
└── requirements.txt         # Dependências do projeto
```
