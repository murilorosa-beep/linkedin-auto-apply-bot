"""
Módulo de triagem e cálculo de compatibilidade semântica (Match Score).
Compara requisitos da vaga com o perfil real do candidato (Murilo Martins - Cloud & Infrastructure).
"""

import re
from typing import Dict, Any, List, Tuple, Optional


class JobMatcher:
    def __init__(self, profile: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
        self.profile = profile
        self.config = config or {}
        self.skills_dict = profile.get("skills_experience_years", {})

        filters_cfg = self.config.get("filters", {})
        self.company_blacklist = [c.lower().strip() for c in filters_cfg.get("company_blacklist", []) if c]
        self.title_blacklist = [t.lower().strip() for t in filters_cfg.get("title_blacklist", []) if t]
              # Competências nucleares do candidato (Multilíngue: EN, PT, ES) - 100% Foco em Infra/Cloud/Sistemas
        self.candidate_core_skills = {
            "azure": 5, "microsoft azure": 5, "cloud": 5, "infrastructure": 5, "infraestrutura": 5, "infraestructura": 5,
            "linux": 5, "debian": 4, "ubuntu": 4, "windows": 4, "windows server": 5,
            "networking": 5, "redes": 5, "cisco": 4, "mikrotik": 3, "vpn": 4, "openvpn": 3, "dns": 4, "dhcp": 4,
            "firewall": 5, "fortigate": 5, "pfsense": 5, "palo alto": 3, "cortafuegos": 5,
            "security": 4, "cybersecurity": 4, "segurança": 4, "cibersegurança": 4, "seguridad": 4,
            "siem": 3, "wazuh": 3, "zabbix": 4, "glpi": 4, "itsm": 3,
            "active directory": 5, "iam": 4, "virtualization": 4, "virtualización": 4, "proxmox": 4, "vmware": 4, "hyper-v": 4,
            "backup": 4, "defender": 3, "microsoft defender": 3, "docker": 3, "devops": 4,
            "sre": 4, "site reliability": 4, "sysadmin": 5, "system administrator": 5,
            "sistemas": 5, "servidores": 5, "bash": 3, "powershell": 4, "shell": 3
        }

        # Padrões de cargos de programação / desenvolvimento que devem ser estritamente bloqueados
        # O perfil é 100% focado em Infraestrutura, Cloud, Sistemas, Redes e Segurança (não é programador/dev)
        self.programming_title_patterns = [
            r"\bsoftware\b",
            r"\bdeveloper\b",
            r"\bdevelop\b",
            r"\bdesenvolvedor\b",
            r"\bdesarrollador\b",
            r"\bprogramador\b",
            r"\bfull[\s-]?stack\b",
            r"\bfront[\s-]?end\b",
            r"\bback[\s-]?end\b",
            r"\bweb\s+developer\b",
            r"\bmobile\s+(?:developer|engineer)\b",
            r"\bios\s+(?:developer|engineer|app)\b",
            r"\bandroid\s+(?:developer|engineer|app)\b",
            r"\bflutter\b",
            r"\breact\b",
            r"\bangular\b",
            r"\bvue(?:\.js)?\b",
            r"\bnode(?:\.js)?\b",
            r"\bjava\b",
            r"\bphp\b",
            r"\bruby\b",
            r"\bgolang\b",
            r"\bc\+\+\b",
            r"\bc#\b",
            r"\b\.net\b",
            r"\bdata\s+engineer\b",
            r"\bdata\s+scientist\b",
            r"\bmachine\s+learning\b",
            r"\b(?:generative\s+)?ai\s+engineer\b",
            r"\bartificial\s+intelligence\b",
            r"\binteligência\s+artificial\b",
            r"\bqa\b",
            r"\btester\b",
            r"\btest\s+(?:automation|engineer|lead|analyst)\b",
            r"\bquality\s+assurance\b",
            r"\bengenheiro\s+de\s+dados\b",
            r"\bcientista\s+de\s+dados\b",
            r"\bengenheiro\s+de\s+software\b",
            r"\bdesenvolvimento\b",
            r"\bprogramação\b",
            r"\bprogramacion\b"
        ]

        # Termos que indicam abertura ativa para contratação internacional e remota (LatAm / Global / B2B)
        self.latam_friendly_keywords = [
            "latam", "latin america", "américa latina", "worldwide", "global remote",
            "anywhere in the world", "work from anywhere", "international remote",
            "contractor", "independent contractor", "w-8ben", "w8ben",
            "deel", "remote.com", "oyster", "south america", "brazil"
        ]

        # Termos que indicam suporte real a Visto e Relocação internacional
        self.visa_sponsorship_keywords = [
            "visa sponsorship", "sponsorship available", "we sponsor", "will sponsor",
            "sponsorship is available", "sponsorship provided", "relocation assistance",
            "relocation package", "relocation support", "visado de trabajo",
            "support for foreign nationals", "willing to sponsor", "h-1b", "h1b",
            "relocate to", "support relocation"
        ]

        # Termos de atalho Espanha / UE (Ley de Startups, Nômade Digital, 2 anos de residência)
        self.spain_fasttrack_keywords = [
            "spain", "españa", "madrid", "barcelona", "valencia", "nómada digital",
            "nomada digital", "ley de startups", "visado de nómada", "visado de trabajo"
        ]

        # Termos que indicam bloqueio estrito para residentes nos EUA
        self.us_only_block_keywords = [
            "must reside in the us", "must reside in the united states",
            "only open to us residents", "only candidates in the us", "must be based in the us",
            "us candidates only", "candidates based in the us",
            "us citizenship required", "u.s. citizen only", "us citizen only",
            "security clearance required", "active secret", "top secret", "ts/sci",
            "w-2 only", "w2 only", "no c2c", "no international", "not open to international"
        ]

        # Palavras e requisitos que indicam vagas incompatíveis (ex: restritas a cidadãos americanos presenciais, ou outras stacks)
        self.non_core_keywords = [
            # Restrições de contratação exclusiva presencial nos EUA
            "security clearance", "active secret", "ts/sci", "top secret",
            # Stacks de desenvolvimento não relacionadas ao perfil
            "oracle integration cloud", "oic developer", "oracle oic", "palantir", "ca gen",
            "salesforce developer", "sap consultant", "cobol", "mainframe",
            "frontend only", "react native", "flutter", "ios developer", "android developer",
            "ui/ux designer", "product designer", "graphic designer",
            # Outras áreas
            "sales representative", "account executive", "marketing specialist", "recruiter"
        ]

    def calculate_match(
        self,
        job_title: str,
        job_description: str = "",
        location: str = "",
        workplace_type: str = "",
        company: str = ""
    ) -> Dict[str, Any]:
        """
        Calcula o Score de Compatibilidade (0% a 100%) entre a vaga e o perfil do candidato.
        Verifica Blacklist de empresas/títulos, viabilidade híbrida e oportunidades de visto/LatAm.
        Retorna:
            - score: int (0 a 100)
            - matched_skills: List[str]
            - recommendation: str ('APPLY', 'CONSIDER', 'SKIP')
            - summary: str
            - is_latam_friendly: bool
            - has_visa_sponsorship: bool
            - is_spain_fasttrack: bool
            - us_only_blocked: bool
        """
        # 0.1 Verificação de Blacklist de Empresa
        if company:
            comp_lower = company.lower().strip()
            for blocked in self.company_blacklist:
                if blocked and blocked in comp_lower:
                    return {
                        "score": 10,
                        "matched_skills": [],
                        "recommendation": "SKIP",
                        "summary": f"Empresa na Blacklist ({company}).",
                        "is_latam_friendly": False,
                        "has_visa_sponsorship": False,
                        "is_spain_fasttrack": False,
                        "us_only_blocked": False
                    }

        # 0.2 Verificação de Blacklist de Palavras no Título
        title_lower = job_title.lower()
        for blocked_title in self.title_blacklist:
            if blocked_title:
                pattern = r"\b" + re.escape(blocked_title) + r"\b"
                if re.search(pattern, title_lower):
                    is_senior_term = blocked_title.lower() in [
                        "senior", "sênior", "sr", "sr.", "lead", "staff", "principal", "director", "head of", "vp", "team lead", "tech lead"
                    ]
                    summary_msg = f"Filtro Pleno/Mid-Level: Vaga Sênior ignorada ('{blocked_title}')" if is_senior_term else f"Filtro de Título: Termo ignorado ('{blocked_title}')"
                    return {
                        "score": 10,
                        "matched_skills": [],
                        "recommendation": "SKIP",
                        "summary": summary_msg,
                        "is_latam_friendly": False,
                        "has_visa_sponsorship": False,
                        "is_spain_fasttrack": False,
                        "us_only_blocked": False
                    }

        # 0.3 Filtro Anti-Programação / Desenvolvimento de Software
        # O candidato é especialista em Infraestrutura, Cloud, Sistemas, Redes e Segurança (não é programador/dev).
        for prog_pattern in self.programming_title_patterns:
            prog_match = re.search(prog_pattern, title_lower)
            if prog_match:
                matched_kw = prog_match.group(0).strip()
                return {
                    "score": 10,
                    "matched_skills": [],
                    "recommendation": "SKIP",
                    "summary": f"Vaga de programação/desenvolvimento ('{matched_kw}'). Foco 100% em Infra/Cloud/Sistemas.",
                    "is_latam_friendly": False,
                    "has_visa_sponsorship": False,
                    "is_spain_fasttrack": False,
                    "us_only_blocked": False
                }

        # 0.4 Filtro de Nível de Senioridade (Foco em Pleno / Mid-Level & Júnior, pulando Sênior/Lead)
        # O candidato possui 24 anos e 5 anos de experiência, com perfil ideal para posições Pleno / Mid-Level.
        exclude_senior = self.config.get("filters", {}).get("exclude_senior", True)
        if exclude_senior:
            senior_patterns = [
                r"\bsenior\b",
                r"\bsênior\b",
                r"\bsr\.?\b",
                r"\blead\b",
                r"\btech\s+lead\b",
                r"\bteam\s+lead\b",
                r"\bprincipal\b",
                r"\bstaff\b",
                r"\bhead\s+of\b",
                r"\bdirector\b",
                r"\bgerente\b"
            ]
            for s_pattern in senior_patterns:
                s_match = re.search(s_pattern, title_lower)
                if s_match:
                    matched_s = s_match.group(0).strip()
                    return {
                        "score": 15,
                        "matched_skills": [],
                        "recommendation": "SKIP",
                        "summary": f"Vaga de nível Sênior/Liderança ('{matched_s}'). Perfil calibrado para Pleno / Mid-Level (5 anos de exp).",
                        "is_latam_friendly": False,
                        "has_visa_sponsorship": False,
                        "is_spain_fasttrack": False,
                        "us_only_blocked": False
                    }

        text_to_analyze = f"{job_title} {job_description} {location}".lower()

        # 1. Verificar se é uma área totalmente incompatível
        for non_core in self.non_core_keywords:
            if non_core in text_to_analyze:
                return {
                    "score": 25,
                    "matched_skills": [],
                    "recommendation": "SKIP",
                    "summary": f"Vaga fora do foco principal (identificado: '{non_core}').",
                    "is_latam_friendly": False,
                    "has_visa_sponsorship": False,
                    "is_spain_fasttrack": False,
                    "us_only_blocked": False
                }

        # 1.1 Verificação geográfica para vagas HÍBRIDAS no Brasil
        # Candidato reside em Jundiaí-SP (viável para Grande SP, Campinas, Barueri, Jundiaí e região)
        is_hybrid = workplace_type.lower() in ("híbrido", "hibrido", "hybrid") or "híbrido" in text_to_analyze or "hybrid" in text_to_analyze
        loc_lower = location.lower()
        if is_hybrid and loc_lower:
            brazil_distant_indicators = [
                "rio de janeiro", ", rj", "curitiba", ", pr", "porto alegre", ", rs",
                "belo horizonte", ", mg", "recife", ", pe", "fortaleza", ", ce",
                "brasília", "brasilia", ", df", "salvador", ", ba", "florianópolis", ", sc",
                "goiânia", ", go", "manaus", ", am", "belém", ", pa"
            ]
            sp_feasible = [
                "são paulo", "sao paulo", "jundiaí", "jundiai", "campinas", "barueri",
                "alphaville", "osasco", "santo andré", "são bernardo", "guarulhos", "sorocaba",
                "valinhos", "vinhedo", "itu", "atibaia", "bragança", ", sp", " sp "
            ]
            has_distant = any(d in loc_lower for d in brazil_distant_indicators)
            has_sp = any(s in loc_lower for s in sp_feasible)
            if has_distant and not has_sp:
                return {
                    "score": 30,
                    "matched_skills": [],
                    "recommendation": "SKIP",
                    "summary": f"Vaga híbrida fora da região de mobilidade viável ({location}). Descartada para poupar cota.",
                    "is_latam_friendly": False,
                    "has_visa_sponsorship": False,
                    "is_spain_fasttrack": False,
                    "us_only_blocked": False
                }

        # 1.2 Análise de Vistos, Contratação Global e Restrições US-Only
        is_latam_friendly = any(kw in text_to_analyze for kw in self.latam_friendly_keywords)
        has_visa_sponsorship = any(kw in text_to_analyze for kw in self.visa_sponsorship_keywords)
        is_spain_fasttrack = any(kw in text_to_analyze for kw in self.spain_fasttrack_keywords)
        us_only_blocked = any(kw in text_to_analyze for kw in self.us_only_block_keywords)

        filters_cfg = self.config.get("filters", {})

        # Filtro estrito: usuário quer APENAS vagas abertas a contratação internacional/B2B
        if filters_cfg.get("only_latam_friendly", False) and us_only_blocked:
            return {
                "score": 20,
                "matched_skills": [],
                "recommendation": "SKIP",
                "summary": "Vaga restrita exclusivamente a residentes dos EUA (US Only / Clearance).",
                "is_latam_friendly": False,
                "has_visa_sponsorship": False,
                "is_spain_fasttrack": False,
                "us_only_blocked": True
            }

        # Filtro estrito: usuário quer APENAS vagas com patrocínio de visto / relocation
        if filters_cfg.get("visa_sponsorship_only", False) and not has_visa_sponsorship:
            return {
                "score": 30,
                "matched_skills": [],
                "recommendation": "SKIP",
                "summary": "Vaga sem menção explícita de patrocínio de visto / relocation.",
                "is_latam_friendly": is_latam_friendly,
                "has_visa_sponsorship": False,
                "is_spain_fasttrack": is_spain_fasttrack,
                "us_only_blocked": us_only_blocked
            }

        matched_skills = []
        weight_sum = 0

        # 2. Avaliação de título da vaga (EN, PT, ES) - 100% Focado em Infra/Cloud/Sistemas/Redes
        title_boost = 0
        if any(w in title_lower for w in [
            "cloud", "infrastructure", "infraestrutura", "infraestructura", "azure", "devops",
            "sre", "sysadmin", "systems", "sistemas", "administrador de sistemas", "arquitecto cloud",
            "platform engineer", "cloud administrator", "cloud engineer", "infrastructure engineer"
        ]):
            title_boost += 35
        elif any(w in title_lower for w in [
            "network", "redes", "security", "segurança", "seguridad", "ciberseguridad",
            "cybersecurity", "firewall", "suporte", "support", "datacenter", "virtualization",
            "virtualização", "systems engineer", "systems administrator", "analista de infraestrutura"
        ]):
            title_boost += 25
        elif any(w in title_lower for w in [
            "engineer", "engenheiro", "ingeniero", "analista", "especialista",
            "administrator", "administrador", "técnico", "tecnico"
        ]):
            title_boost += 15

        # 3. Análise de palavras-chave da descrição
        for skill, weight in self.candidate_core_skills.items():
            pattern = r"\b" + re.escape(skill) + r"\b"
            if re.search(pattern, text_to_analyze):
                matched_skills.append(skill.title())
                weight_sum += weight

        # Normalização do score: título (até 35) + skills encontradas (até 65)
        skills_score = min(65, weight_sum * 4)
        total_score = min(100, max(20, title_boost + skills_score))

        # Se houver pouca descrição (ex: LinkedIn truncou), o título garante uma base razoável
        if not job_description and title_boost > 0:
            total_score = max(total_score, 65)

        # 4. Bônus de Oportunidades Internacionais Estratégicas
        badge_tags = []
        if has_visa_sponsorship:
            total_score = min(100, total_score + 15)
            badge_tags.append("✈️ Patrocínio de Visto")
        if is_latam_friendly:
            total_score = min(100, total_score + 10)
            badge_tags.append("🌎 LatAm/B2B")
        if is_spain_fasttrack:
            total_score = min(100, total_score + 8)
            badge_tags.append("🇪🇸 Rota Espanha/UE")

        tag_prefix = f"[{' | '.join(badge_tags)}] " if badge_tags else ""

        # Recomendação
        if total_score >= 70 or has_visa_sponsorship:
            recommendation = "APPLY"
            summary = f"{tag_prefix}Excelente compatibilidade ({total_score}%). Forte alinhamento em {', '.join(matched_skills[:3]) or 'Cloud & Infra'}."
        elif total_score >= 50:
            recommendation = "CONSIDER"
            summary = f"{tag_prefix}Boa compatibilidade ({total_score}%). Tecnologias compatíveis: {', '.join(matched_skills[:3]) or 'Engenharia de TI'}."
        else:
            recommendation = "SKIP"
            summary = f"{tag_prefix}Compatibilidade moderada/baixa ({total_score}%)."

        return {
            "score": int(total_score),
            "matched_skills": list(set(matched_skills)),
            "recommendation": recommendation,
            "summary": summary,
            "is_latam_friendly": is_latam_friendly,
            "has_visa_sponsorship": has_visa_sponsorship,
            "is_spain_fasttrack": is_spain_fasttrack,
            "us_only_blocked": us_only_blocked
        }
