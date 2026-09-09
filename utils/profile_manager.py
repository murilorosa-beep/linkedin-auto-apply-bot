"""
Gerenciador do perfil do candidato (config/profile.yaml) e upload de currículo.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any

PROFILE_PATH = Path("config/profile.yaml")
CV_DIR = Path("config/cv")
RESUME_PATH = CV_DIR / "resume.pdf"
RESUME_PATH_EN = CV_DIR / "resume_en.pdf"
RESUME_PATH_PT = CV_DIR / "resume_pt.pdf"


def load_profile() -> Dict[str, Any]:
    """Carrega os dados do perfil."""
    if not PROFILE_PATH.exists():
        return {}
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_profile(profile_data: Dict[str, Any]):
    """Salva os dados atualizados do perfil."""
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.dump(profile_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def save_uploaded_resume(file_bytes: bytes, lang: str = "en") -> bool:
    """Salva o arquivo PDF de currículo (en para internacional ou pt para nacional)."""
    try:
        CV_DIR.mkdir(parents=True, exist_ok=True)
        if lang == "pt":
            target = RESUME_PATH_PT
        else:
            target = RESUME_PATH_EN
            # Sincroniza também com resume.pdf para compatibilidade legada
            with open(RESUME_PATH, "wb") as f_legacy:
                f_legacy.write(file_bytes)

        with open(target, "wb") as f:
            f.write(file_bytes)
        return True
    except Exception:
        return False


def has_resume(lang: str = "en") -> bool:
    """Verifica se o arquivo de currículo em PDF existe para o idioma especificado."""
    if lang == "pt":
        return RESUME_PATH_PT.exists() and RESUME_PATH_PT.stat().st_size > 0
    # Internacional: verifica resume_en.pdf ou o legado resume.pdf
    if RESUME_PATH_EN.exists() and RESUME_PATH_EN.stat().st_size > 0:
        return True
    return RESUME_PATH.exists() and RESUME_PATH.stat().st_size > 0


def has_resume_pt() -> bool:
    return has_resume("pt")


def has_resume_en() -> bool:
    return has_resume("en")


def get_resume_path(lang: str = "en") -> str:
    """Retorna o caminho absoluto do currículo para o idioma."""
    if lang == "pt" and has_resume("pt"):
        return str(RESUME_PATH_PT.resolve())
    if has_resume("en"):
        if RESUME_PATH_EN.exists():
            return str(RESUME_PATH_EN.resolve())
        return str(RESUME_PATH.resolve())
    # Fallback geral
    if RESUME_PATH.exists():
        return str(RESUME_PATH.resolve())
    if RESUME_PATH_PT.exists():
        return str(RESUME_PATH_PT.resolve())
    return str(RESUME_PATH.resolve())


def extract_cv_text(lang: str = "en") -> str:
    """Extrai o texto completo do arquivo de currículo usando pypdf."""
    path_str = get_resume_path(lang)
    if not os.path.exists(path_str):
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path_str)
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n".join(text_parts).strip()
    except Exception:
        return ""


def get_cv_stats(lang: str = "en") -> Dict[str, Any]:
    """Retorna estatísticas sobre o currículo atual do idioma selecionado."""
    text = extract_cv_text(lang)
    if not text:
        return {"exists": False, "word_count": 0, "preview": "", "path": get_resume_path(lang)}
    words = len(text.split())
    preview = text[:350] + ("..." if len(text) > 350 else "")
    return {
        "exists": True,
        "word_count": words,
        "preview": preview,
        "full_text": text,
        "path": get_resume_path(lang)
    }
