# XTraccar Simulator

[English](README.md) · [Español](README.es.md) · **Português**

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G7B227FYIH)

Simulador de veículo para testes e demonstrações no [Traccar](https://www.traccar.org/) via protocolo HTTP **OsmAnd** (porta **5055**). O veículo segue **ruas reais** (OpenStreetMap + **OSRM**) ou um arquivo **GPX**, com dinâmica de velocidade, telemetria realista e painel web ao vivo.

> Disponível para quem precisa testar integrações Traccar/OsmAnd. Não é um projeto open source com licença pública de contribuição.

**Idiomas do painel:** **inglês**, **espanhol** e **português** (menu de bandeiras na barra superior; salvo no navegador).

![Painel web com mapa Leaflet](docs/screenshot.png)

---

## Índice

1. [Colocar tudo no ar](#colocar-tudo-no-ar)
2. [Parar e reiniciar](#parar-e-reiniciar)
3. [Funcionalidades](#funcionalidades)
4. [Configuração](#configuração-configyaml--painel)
5. [Uso do painel](#uso-do-painel)
6. [Telemetria](#telemetria)
7. [API REST](#api-rest)
8. [Solução de problemas](#solução-de-problemas)
9. [Estrutura do projeto](#estrutura-do-projeto)
10. [Distribuição](#distribuição)

---

## Colocar tudo no ar

Você precisa de **dois serviços**: **Traccar** (recebe posições) e este **simulador** (painel + envios OsmAnd).

### 1. Traccar

1. Instale e inicie o Traccar ([traccar.org](https://www.traccar.org/)).
2. Confirme que **OsmAnd** escuta na porta **5055**.
3. Crie um **dispositivo** e anote o **identificador único**.
4. Use o mesmo valor em `device_id` do simulador (`config.yaml`).
5. Abra o firewall **TCP 5055** entre o PC do simulador e o Traccar.

**URL OsmAnd típica:** `http://IP_TRACCAR:5055/`

### 2. Primeira instalação (Windows)

```powershell
cd "C:\Users\...\XTraccar Simulator"
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy config.example.yaml config.yaml
notepad config.yaml
```

Edite pelo menos `traccar_url` e `device_id`. **`config.yaml` está no `.gitignore`**.

**Valores padrão** (`config.example.yaml`):

| Campo | Valor |
|-------|--------|
| `default_lat` / `default_lon` | **-22.7487**, **-48.5837** |
| `cell_mcc` / `mnc` / `lac` / `cid` | **724** / **5** / **43714** / **45086** |
| Intervalos envio (ign ON / OFF) | **5 s** / **60 s** |
| Painel | **http://127.0.0.1:8081** |

### 3. Iniciar o simulador

- **Windows:** duplo clique em **`iniciar.bat`** (libera a porta **8081**).
- **Manual:** `.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8081`

Painel **8081** · Traccar OsmAnd **5055**.

### 4. Verificar

- http://127.0.0.1:8081  
- http://127.0.0.1:8081/api/health → `"version": "2.1"`

### 5. Primeiro teste com Traccar

1. Painel → **Configurações** → URL + Device ID → **Salvar** → **Testar conexão**.
2. Verifique **Última comunicação** no Traccar.

### 6. Linux / macOS

```bash
cd "XTraccar Simulator"
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml
uvicorn app.main:app --host 127.0.0.1 --port 8081
```

---

## Parar e reiniciar

| Ação | Como |
|--------|------|
| Parar simulador | **Ctrl+C** na janela do uvicorn |
| Reiniciar (Windows) | Executar **`iniciar.bat`** de novo |
| Porta 8081 ocupada | `iniciar.bat` ou encerrar o processo |
| Após mudanças | Reiniciar uvicorn; **Ctrl+F5** no navegador |

Inicie o **Traccar primeiro**, depois o simulador.

---

## Funcionalidades

| Área | Capacidades |
|------|-------------|
| **Mapa** | Leaflet, OSM/HOT, waypoints, OSRM, GPX, Seguir (zoom mín. 16), HUD |
| **Viagem** | Iniciar, pausar/retomar (**Espaço**), parar |
| **Traccar** | Heartbeat, intervalos ign ON/OFF, teste HTTP, log |
| **Veículo** | Ignição, 12V, bloqueio, odômetro |
| **Telemetria** | RPM, combustível, célula, Wi‑Fi, alarmes, entradas digitais |
| **GPX** | Exportar trilha; replay ponto a ponto |
| **UI** | EN/ES/PT, tema claro/escuro |
| **Automação** | REST + WebSocket `/ws/live` |

---

## Configuração (`config.yaml` / painel)

Carrega **`config.yaml`** na inicialização (se não existir, defaults do código).

| Chave | Descrição |
|-------|-----------|
| `traccar_url` | URL base OsmAnd |
| `device_id` | Unique id no Traccar |
| `interval_ignition_on` / `off` | Intervalo de envio (s) |
| `osrm_base_url` | API OSRM |
| `traffic_profile` | `low` \| `normal` \| `heavy` |
| `default_lat` / `default_lon` | Centro do mapa |
| `odometer_base_km` | Odômetro inicial (km) |
| `cell_*` | Torre simulada |
| `driver_unique_id` | Motorista OsmAnd (opcional) |
| `map_style` | `osm` ou `hot` |

Variáveis de ambiente: prefixo **`TRACCAR_SIM_`**.

---

## Uso do painel

1. **Configurações** → URL Traccar + Device ID → **Salvar** → **Testar conexão**.
2. **Rota** → cliques no mapa (2+ pontos) → **Calcular rota (OSRM)** ou **GPX**.
3. Odômetro opcional → **OK**.
4. **Iniciar** — observe o Traccar e o HUD.

---

## Telemetria

- **Odômetro:** parâmetro **`odometer`** em **metros**.
- **RPM:** 0 com ignição off; marcha lenta parado; sobe com a velocidade em movimento.
- **Célula padrão:** `724,5,43714,45086` (parâmetro OsmAnd `cell=`).

---

## API REST

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/status` | Estado completo |
| GET | `/api/health` | Versão |
| PUT | `/api/settings` | Ajustes |
| POST | `/api/route/osrm` \| `/api/route/gpx` | Rotas |
| POST | `/api/simulation/start` \| `stop` \| `pause` | Viagem |
| POST | `/api/vehicle/*` | Ignição, bloqueio, 12V, odômetro, digital |
| GET | `/api/trail/export.gpx` | Exportar trilha |
| POST | `/api/replay/start` \| `stop` | Replay GPX |
| POST | `/api/traccar/test` | Teste de envio |
| WS | `/ws/live` | Ticks ao vivo |

---

## Solução de problemas

| Problema | Verificar |
|----------|-----------|
| Painel 404 | Uvicorn na **8081**, `/api/health` |
| Traccar não atualiza | Mesmo `device_id`, URL `:5055`, firewall |
| OSRM falha | Limites do servidor público — use OSRM próprio |
| UI antiga | **Ctrl+F5** |

---

## Estrutura do projeto

```
app/static/     # Painel (i18n.js, locales.js, app.js)
app/simulation/ # Motor e telemetria
app/routing/    # OSRM e GPX
app/traccar/    # Cliente OsmAnd HTTP
config.example.yaml
iniciar.bat     # Launcher Windows (8081)
```

---

## Distribuição

Você pode **instalar e compartilhar** este pacote para testes Traccar.

**Checklist:** Python 3.11+ → `pip install -e .` → `config.yaml` → Traccar :5055 → `iniciar.bat` → http://127.0.0.1:8081
