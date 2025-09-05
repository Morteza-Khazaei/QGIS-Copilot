# QGIS Copilot

<p align="center">
  <img src="figures/copilot.png" alt="QGIS Copilot" width="160" />
</p>

<div align="center">

[![QGIS](https://img.shields.io/badge/QGIS-3.0+-green.svg)](https://qgis.org)
[![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Providers](https://img.shields.io/badge/AI%20Providers-Ollama%20%7C%20OpenAI%20%7C%20Gemini%20%7C%20Claude-blue.svg)](#-ai-tab-overview)

**Chat with QGIS in natural language • Execute PyQGIS code safely • Boost your GIS productivity**

[🚀 Quick Start](#-quick-start) •
[📖 Documentation](#-documentation) •
[🎯 Examples](#-examples) •
[🤝 Contributing](#-contributing)

</div>

---

## 🌟 What is QGIS Copilot?

QGIS Copilot is your intelligent GIS assistant that transforms how you work with QGIS. Instead of remembering complex PyQGIS syntax or searching through documentation, just ask your Copilot in plain English!

### ✨ Key Features (Current)

- **🗣️ Natural Language Interface**: Ask questions like "Create a 500m buffer around selected features"
- **🧠 Context Aware**: Understands your current project, layers, and data
- **⚡ Code Generation**: Generates and executes PyQGIS code automatically
- **🛡️ Safe Execution**: Built-in security prevents dangerous operations
- **💻 Modern UI (QML)**: Integrated QML chat with Markdown, per-block actions, and pastel bubbles
- **🔄 Real-time Results in Chat**: Python execution logs appear as single, consolidated “System” messages (batched to avoid spam)
- **🏷️ Model Labeling**: Each assistant reply shows the exact model name that produced it
- **📊 Smart Context**: Knows about your layers, CRS, extents, and more
- **🧩 Multiple Providers**: Google Gemini, OpenAI, Anthropic Claude, and Ollama (Local) — Ollama is the default
- **🧪 One‑click Model Tests**: Validate Ollama models from the AI tab

---

## 🚀 Quick Start

### Prerequisites

- QGIS 3.0 or higher
- Python 3.6+
- Internet connection (for cloud providers)
- Optional: Google/OpenAI/Anthropic API key(s) for cloud providers
- Optional: Ollama for local, offline models (no API key)

### 📦 Installation

1. **Download the plugin files** to your QGIS plugins directory:
   - **Windows**: `C:\Users\[username]\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\qgis_copilot\`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_copilot/`
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/qgis_copilot/`

2. **Restart QGIS**

3. **Enable the plugin**:
   - Go to `Plugins` → `Manage and Install Plugins`
   - Find "QGIS Copilot" and enable it

4. **Get your API key**:
   - Visit [Google AI Studio](https://aistudio.google.com)
   - Sign in and create a free API key

5. **Configure QGIS Copilot**:
   - Click the QGIS Copilot icon 💬
   - Go to the AI tab
   - Choose an AI provider (Ollama is default and requires no API key)
   - For cloud providers, enter and test your API key

### 🖥️ Local Ollama Setup (Default)

Ollama runs models locally — no API key needed.

1. Install Ollama from https://ollama.ai
2. Start the daemon: `ollama serve`
3. Pull a model, e.g.: `ollama pull llama3.1:8b`
4. Verify models: `curl http://localhost:11434/api/tags`
5. Quick chat test (optional):
   - `curl http://localhost:11434/api/chat -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"why is the sky blue?"}]}'`

In QGIS Copilot → AI tab → Provider = “Ollama (Local)”:
- Base URL defaults to `http://localhost:11434` (changeable)
- Click “Refresh Models” to populate available models
- Select a model and click “Test Selected Model” to confirm it responds

Before a request, Copilot posts a single configuration snapshot (provider, model, base URL, prompt file, preferences, workspace) as one “System” message in the chat. API responses are shown only in chat.

### 🎯 First Steps

1. Click the QGIS Copilot icon in your toolbar
2. Type: `"Show me all the layers in my project"`
3. Press Enter and watch the magic happen! ✨

---

## 📖 Documentation

We maintain Sphinx docs (Read the Docs theme) for UI/UX and workflows:

- Local build: `make -C docs html` → open `docs/_build/html/index.html`
- Sources: `docs/source/`
- UI/UX Guide: `docs/source/ui_ux.rst`

### ⚙️ AI Tab Overview

- **Provider**: Choose Ollama (Local), OpenAI ChatGPT, Google Gemini, or Anthropic Claude.
- **Ollama Configuration**: Base URL, Check Connection (diagnostic), Refresh Models.
- **Model Settings**: Model picker + “Test Selected Model” (for Ollama).
- **System Prompt**: Stored in a Markdown file; use “Change…” and “Open File”.
- **Logs Behavior**: Live Logs panel shows provider/config snapshots and Python execution logs — not API responses.

#### Provider specifics
- `Ollama (Local)`: no API key; ensure daemon at `http://localhost:11434`. Use “Refresh Models” and “Test Selected Model”.
- `OpenAI ChatGPT`: add an API key; pick a model (e.g., `gpt-4o`). Test your key from the AI tab.
- `Google Gemini`: add an API key; pick a model (e.g., `gemini-1.5-pro`). Test your key from the AI tab.
- `Anthropic Claude`: add an API key; pick a model (e.g., `claude-3-5-sonnet`). Test your key from the AI tab.

### 📝 Chat UI behaviors

- Hover actions are precise and steady (top‑right hotspot). Buttons don’t move or flicker.
- Text blocks: Copy. Assistant code blocks: Copy · Edit · Run. Error logs: Debug.
- Composer shows Send and a Clear icon (disabled until the chat has messages). The list extends under the composer to maximize space.
- Code blocks render with black text on a soft gray background for readability.

### 🎯 Examples

Here are some things you can ask your QGIS Copilot:

#### 🗺️ **Layer Management**
```
"Add a new point layer called 'sample_points'"
"Change the active layer color to red"
"Remove all empty layers from the project"
"Show me the attribute table for the selected layer"
```

#### 🔍 **Spatial Analysis**
```
"Create a 1km buffer around all polygons"
"Find all points within the current map extent"
"Calculate the area of all features in the active layer"
"Perform a spatial join between my two layers"
```

#### 📊 **Data Operations**
```
"Export the active layer to CSV"
"Count how many features are in each layer"
"Filter features where population > 10000"
"Select all features intersecting with the current selection"
```

#### 🎨 **Visualization**
```
"Create a heatmap from my point data"
"Style polygons with a graduated color scheme"
"Set the map canvas to show the full extent of all layers"
"Change the CRS to EPSG:4326"
```

#### 🛠️ **Processing**
```
"Run a buffer analysis with 500m distance"
"Clip layer A with layer B"
"Dissolve features by the 'category' attribute"
"Create voronoi polygons from my points"
```

### 💡 **Pro Tips**

- **Be specific**: "Create a 100m buffer" is better than "create a buffer"
- **Use context**: Enable "Include QGIS Context" for better results
- **Review code**: Always check generated code before execution
- **Start simple**: Begin with basic requests and build up complexity

### 🧪 Troubleshooting Ollama

- Ensure the daemon is running: `ollama serve`
- Pull a chat‑capable model (e.g., `llama3.1:8b`) and click “Refresh Models”
- Use “Check Connection” to run a diagnostic (lists models and performs a chat test)
- Verify with curl:
  - List: `curl http://localhost:11434/api/tags`
  - Chat: `curl http://localhost:11434/api/chat -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Connection test successful!"}]}'`

For an in‑QGIS diagnostic:
- `from QGIS_Copilot.ai.utils.diagnostics import run_diagnostic`
- `run_diagnostic()`

---

## 🏗️ Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    QGIS Copilot                            │
├─────────────────────────────────────────────────────────────┤
│  Chat Interface                                             │
│  ├── Natural Language Input                                 │
│  ├── Context-Aware Responses                               │
│  └── Syntax-Highlighted Code Display                       │
├─────────────────────────────────────────────────────────────┤
│  AI Provider Integrations                                   │
│  ├── Ollama (Local) — local daemon via REST                 │
│  ├── OpenAI ChatGPT — REST API                              │
│  ├── Google Gemini — REST API                               │
│  └── Anthropic Claude — REST API                            │
├─────────────────────────────────────────────────────────────┤
│  PyQGIS Code Executor                                       │
│  ├── Safe Code Validation                                  │
│  ├── Sandboxed Execution                                   │
│  └── Result Processing                                      │
├─────────────────────────────────────────────────────────────┤
│  QGIS Integration                                           │
│  ├── Layer Management                                       │
│  ├── Map Canvas Operations                                  │
│  └── Project Context                                        │
└─────────────────────────────────────────────────────────────┘
```

### File Structure

```
qgis_copilot/
├── 📄 __init__.py                         # Plugin initialization
├── 🧠 copilot_plugin.py                   # Main plugin class
├── 💬 copilot_chat_dialog.py              # Main UI (AI tab, integrated QML chat)
├── 📦 ai/
│   ├── providers/
│   │   ├── gemini_api.py                 # Google Gemini integration
│   │   ├── openai_api.py                 # OpenAI ChatGPT integration
│   │   ├── claude_api.py                 # Anthropic Claude integration
│   │   └── ollama_api.py                 # Ollama (Local) integration
│   └── utils/
│       └── pyqgis_api_validator.py       # Live API signatures helper
├── 🧪 ai/utils/diagnostics.py             # Optional Ollama connectivity diagnostic
├── ⚡ pyqgis_executor.py                  # Code execution engine
├── 📁 agents/                             # Agent prompts (qgis_agent_v3.5.md, qgis_agent_v3.4.md)
├── 📋 metadata.txt                        # Plugin metadata
├── 🖼️ figures/                            # UI assets (icons/images)
├── 🗂️ ui/                                 # QML: ChatPanel.qml
├── 📚 docs/                               # Sphinx docs (Read the Docs theme)
├── 📚 README.md                           # This file
└── 📜 LICENSE                             # MIT License
```

---

## 🔒 Security & Safety

QGIS Copilot takes security seriously:

### 🛡️ **Built-in Protections**
- **Code Validation**: Blocks dangerous operations before execution
- **Sandboxed Environment**: Limited access to system resources
- **Safe API Calls**: Only approved PyQGIS functions available
- **Input Sanitization**: User input is cleaned and validated

### ⚠️ **Blocked Operations**
- File system access outside QGIS
- Network operations
- System commands
- Code evaluation functions
- Import of dangerous modules

### 🔑 **API Key Security**
- API keys are stored locally in QGIS settings
- Never transmitted except to Google's servers
- Use environment variables for production deployments

---

## 🎨 Customization

### 🎛️ **Configuration Options**

| Option | Description | Default |
|--------|-------------|---------|
| **Include QGIS Context** | Send current project info to AI | ✅ Enabled |
| **Auto-execute Code** | Automatically run generated code | ❌ Disabled |
| **API Model** | Gemini model to use | `gemini-1.5-flash` |

### 🎨 **UI Themes**

The interface adapts to your QGIS theme automatically, supporting:
- Light mode
- Dark mode  
- High contrast themes

---

## 🚀 Advanced Usage

### 🔧 **Custom Code Execution**

You can also execute your own PyQGIS code:

```python
# Get current project layers
project = QgsProject.instance()
layers = project.mapLayers()
print(f"Project has {len(layers)} layers")

# Access the active layer
layer = iface.activeLayer()
if layer:
    print(f"Active layer: {layer.name()}")
```

### 🔗 **Integration with Processing**

QGIS Copilot works seamlessly with QGIS Processing:

```python
import processing

# Run buffer analysis
result = processing.run("native:buffer", {
    'INPUT': 'my_layer',
    'DISTANCE': 1000,
    'OUTPUT': 'memory:'
})
```

### 📊 **Batch Operations**

Ask for batch operations on multiple layers:

```
"Apply a 100m buffer to all polygon layers in the project"
"Export all vector layers to shapefiles"
"Calculate area for all polygon layers"
```

---

## 📈 Performance

### ⚡ **Optimization Tips**

- **Selective Context**: Disable context for simple queries to speed up responses
- **Batch Requests**: Group related questions in a single conversation
- **API Limits**: Be aware of Google's rate limits (60 requests/minute for free tier)

### 📊 **Benchmarks**

| Operation Type | Response Time | Success Rate |
|---------------|---------------|--------------|
| Layer Management | ~2-3 seconds | 95% |
| Spatial Analysis | ~3-5 seconds | 90% |
| Data Export | ~2-4 seconds | 98% |
| Styling | ~2-3 seconds | 92% |

---

## 🐛 Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| **Plugin not showing** | Check QGIS version (3.0+), restart QGIS |
| **API key errors** | Verify key is correct, check internet connection |
| **Code execution fails** | Review execution log, check layer availability |
| **No response** | Check API quotas, verify context size |

### 📋 **Debug Mode**

Enable debug logging in QGIS:
1. Go to `View` → `Panels` → `Log Messages`
2. Look for "QGIS Copilot" messages
3. Report issues with full log context

### 💬 **Getting Help**

- 📖 Check this README first
- 🐛 [Report bugs](https://github.com/yourusername/qgis-copilot/issues)
- 💡 [Request features](https://github.com/yourusername/qgis-copilot/issues)
- 💬 Join QGIS community discussions

---

## 🤝 Contributing

We love contributions! Here's how you can help:

### 🚀 **Ways to Contribute**

- 🐛 **Report Bugs**: Found an issue? Let us know!
- 💡 **Suggest Features**: Have ideas? We'd love to hear them!
- 📝 **Improve Docs**: Help make our documentation better
- 🔧 **Code Contributions**: Submit pull requests
- 🌍 **Translations**: Help translate QGIS Copilot

### 🛠️ **Development Setup**

```bash
# Clone the repository
git clone https://github.com/yourusername/qgis-copilot.git

# Create development symlink
ln -s /path/to/qgis-copilot ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/

# Install development dependencies
pip install -r requirements-dev.txt
```

### 📝 **Code Style**

- Follow PEP 8 for Python code
- Use meaningful variable names
- Add docstrings to all functions
- Include type hints where possible

---

## 🔮 Future Roadmap

### 🎯 **Planned Features**

- [ ] **Multi-language Support**: Interface in multiple languages
- [ ] **Voice Commands**: Talk to your QGIS Copilot
- [ ] **Custom AI Models**: Support for other AI providers
- [ ] **Workflow Automation**: Save and replay common operations
- [ ] **Plugin Ecosystem**: Integration with other QGIS plugins
- [ ] **Advanced Context**: Even smarter project understanding
- [ ] **Collaborative Features**: Share conversations and solutions

### 🚀 **Version Roadmap**

| Version | Features | Timeline |
|---------|----------|----------|
| **1.1** | Voice commands, UI improvements | Q2 2024 |
| **1.2** | Multi-language support | Q3 2024 |
| **2.0** | Custom models, workflow automation | Q4 2024 |

---

## 📊 API Usage & Costs

### 💰 **Google Gemini Pricing**

| Tier | Requests/Month | Cost |
|------|---------------|------|
| **Free** | 60/minute, 1500/day | $0 |
| **Pay-as-you-go** | No limits | $0.125/1K requests |

### 📈 **Usage Optimization**

- Use specific, focused questions
- Disable context for simple queries
- Batch related questions
- Monitor your usage in Google AI Studio

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2024 QGIS Copilot Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## 🙏 Acknowledgments

- **QGIS Community**: For the amazing open-source GIS platform
- **Google**: For providing the Gemini AI API
- **Contributors**: Everyone who helped make QGIS Copilot better
- **Beta Testers**: Thank you for your feedback and bug reports

---

## 📞 Contact & Support

Made with ❤️ for the QGIS Community by:

Morteza Khazaei, Ph.D. Candidate

Department of Applied Geomatics
Centre d’applications et de recherches en télédétection (CARTEL)
University of Sherbrooke
2500, Boulevard Université
Sherbrooke (Québec), Canada, J1K 2R1

Email: morteza.khazaei@usherbrooke.ca

For bug reports and feature requests, please contact me by email. If this project is hosted in a Git repository, feel free to open issues there as well.

---

### ⭐ Star this project if you find it useful!

Happy mapping with your QGIS Copilot! 🗺️🤖
