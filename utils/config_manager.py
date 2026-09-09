"""
Gerenciador de configurações (config/config.yaml) para a interface Streamlit.
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any

CONFIG_PATH = Path("config/config.yaml")
ENV_PATH = Path(".env")


def load_config() -> Dict[str, Any]:
    """Carrega o arquivo de configuração atual."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_profile() -> Dict[str, Any]:
    """Carrega o perfil do candidato (config/profile.yaml)."""
    from utils.profile_manager import load_profile as _lp
    return _lp()


def save_config(config_data: Dict[str, Any]):
    """Salva os dados de configuração atualizados no YAML."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def set_dry_run(dry_run_state: bool):
    """Atualiza o estado de dry_run preservando os comentários do arquivo."""
    if not CONFIG_PATH.exists():
        return
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    new_val = "true" if dry_run_state else "false"
    content = re.sub(r"dry_run:\s*(true|false)", f"dry_run: {new_val}", content, count=1, flags=re.IGNORECASE)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def set_api_key(env_var_name: str, key_value: str):
    """Salva a chave de API no arquivo .env local."""
    env_content = ""
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            env_content = f.read()

    pattern = rf"^{env_var_name}=.*$"
    replacement = f'{env_var_name}="{key_value.strip()}"'
    if re.search(pattern, env_content, flags=re.MULTILINE):
        env_content = re.sub(pattern, replacement, env_content, flags=re.MULTILINE)
    else:
        env_content += f"\n{replacement}"

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(env_content.strip() + "\n")
    os.environ[env_var_name] = key_value.strip()


def apply_preset(preset_name: str) -> bool:
    """Aplica e salva imediatamente o preset especificado ('spain', 'international' ou 'brazil') em config.yaml."""
    cfg = load_config()
    presets = cfg.get("search", {}).get("presets", {})
    if preset_name not in presets:
        return False

    preset_data = presets[preset_name]
    cfg["search"]["preset"] = preset_name
    cfg["search"]["keywords"] = list(preset_data.get("keywords", []))
    cfg["search"]["locations"] = list(preset_data.get("locations", []))
    cfg["search"]["workplace_types"] = list(preset_data.get("workplace_types", ["remote", "hybrid", "on_site"]))
    cfg["search"]["remote_only"] = preset_data.get("workplace_types") == ["remote"]

    save_config(cfg)
    return True
