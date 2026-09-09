"""
Módulo de Otimização e Análise de Compatibilidade ATS (Applicant Tracking Systems).
Compara a descrição da vaga com o perfil real do candidato para identificar lacunas de palavras-chave
e sugerir bullet points de experiência em inglês/espanhol para furar os filtros automatizados de RH.
"""

import re
from typing import Dict, Any, List, Tuple, Set


class ATSOptimizer:
    # Taxonomia técnica de palavras-chave de alta frequência em Cloud, Infra e DevOps
    TECH_TAXONOMY = {
        # Cloud & Azure
        "azure": ["azure", "microsoft azure", "azure cloud", "portal azure"],
        "entra_id": ["entra id", "azure ad", "active directory", "azure active directory", "iam"],
        "azure_networking": ["vnet", "virtual network", "expressroute", "nsg", "network security group", "vpn gateway", "azure dns"],
        "azure_compute": ["azure vm", "virtual machines", "app service", "azure functions", "serverless"],
        "azure_storage": ["blob storage", "azure storage", "storage account", "azure files"],
        "azure_monitor": ["azure monitor", "log analytics", "application insights", "kql"],

        # Infraestrutura como Código (IaC) & Automação
        "terraform": ["terraform", "hashicorp terraform", "tfstate", "hcl"],
        "ansible": ["ansible", "playbooks", "ansible automation"],
        "bicep": ["bicep", "arm templates", "azure resource manager"],
        "scripting": ["bash", "powershell", "python", "shell scripting"],

        # Containers & Orquestração
        "docker": ["docker", "docker compose", "containerization", "containers"],
        "kubernetes": ["kubernetes", "k8s", "aks", "azure kubernetes service", "helm"],

        # CI/CD & DevOps
        "ci_cd": ["ci/cd", "ci-cd", "continuous integration", "continuous deployment", "pipelines"],
        "github_actions": ["github actions", "github workflows"],
        "azure_devops": ["azure devops", "vsts", "azure pipelines"],
        "git": ["git", "github", "gitlab"],

        # Sistemas Operacionais & Virtualização
        "linux": ["linux", "debian", "ubuntu", "centos", "red hat", "rhel"],
        "windows_server": ["windows server", "active directory", "gpo", "dns", "dhcp", "iis"],
        "virtualization": ["proxmox", "vmware", "vsphere", "hyper-v", "kvm"],

        # Segurança & Compliance
        "security": ["cybersecurity", "cibersegurança", "segurança da informação", "zero trust"],
        "firewall": ["firewall", "fortigate", "pfsense", "palo alto", "cortafuegos"],
        "siem": ["siem", "wazuh", "soc", "incident response"],

        # Observabilidade & SRE
        "monitoring": ["zabbix", "datadog", "prometheus", "grafana", "monitoring", "observability", "sre"]
    }

    def __init__(self, profile: Dict[str, Any], resume_text: str = ""):
        self.profile = profile
        self.resume_text = (resume_text or "").lower()
        self.skills_dict = profile.get("skills_experience_years", {})
        self.certifications = profile.get("certifications", [])
        self._build_candidate_skill_set()

    def _build_candidate_skill_set(self):
        """Compila conjunto normalizado de competências conhecidas do candidato."""
        self.candidate_skills: Set[str] = set()

        # Adiciona skills declaradas no profile.yaml
        for skill in self.skills_dict.keys():
            self.candidate_skills.add(skill.lower().replace("_", " "))

        # Adiciona certificações
        cert_text = " ".join(self.certifications).lower()
        if "az-104" in cert_text:
            self.candidate_skills.update(["az-104", "azure administrator", "azure", "microsoft azure"])
        if "az-900" in cert_text:
            self.candidate_skills.update(["az-900", "azure fundamentals"])

        # Extrai termos presentes no texto do currículo
        for category, aliases in self.TECH_TAXONOMY.items():
            for alias in aliases:
                if alias in self.resume_text:
                    self.candidate_skills.add(alias)
                    self.candidate_skills.add(category.replace("_", " "))

    def analyze_job(self, job_title: str, job_description: str) -> Dict[str, Any]:
        """
        Analisa o anúncio da vaga contra o perfil e currículo do candidato.
        Retorna:
            - ats_match_percentage: int (0 - 100)
            - matched_keywords: List[str]
            - missing_keywords: List[str]
            - key_recommendations: List[str]
            - tailored_experience_bullets: List[str]
        """
        full_job_text = f"{job_title} {job_description}".lower()

        required_categories: Set[str] = set()
        matched_terms: List[str] = []
        missing_terms: List[str] = []

        # Rastreia quais tecnologias a vaga exige
        for category, aliases in self.TECH_TAXONOMY.items():
            cat_found = False
            for alias in aliases:
                pattern = r"\b" + re.escape(alias) + r"\b"
                if re.search(pattern, full_job_text):
                    required_categories.add(category)
                    cat_found = True
                    # Verifica se o candidato possui essa competência
                    if any(alias in s or s in alias for s in self.candidate_skills):
                        matched_terms.append(alias.title())
                    else:
                        missing_terms.append(alias.title())
                    break

        # Evita duplicatas mantendo ordem
        matched_unique = list(dict.fromkeys(matched_terms))
        missing_unique = list(dict.fromkeys(missing_terms))

        # Cálculo do Match ATS baseado nas categorias requeridas pela vaga
        if required_categories:
            matched_cats = [
                cat for cat in required_categories
                if any(any(alias in s for s in self.candidate_skills) for alias in self.TECH_TAXONOMY[cat])
            ]
            ats_match = int((len(matched_cats) / len(required_categories)) * 100)
        else:
            ats_match = 75  # Valor base caso descrição seja concisa

        # Gera recomendações estratégicas
        recommendations = []
        if "Terraform" in missing_unique or "Bicep" in missing_unique:
            recommendations.append("Destaque no seu resumo que você gerencia recursos no Azure com Infrastructure as Code (IaC).")
        if "Docker" in missing_unique or "Kubernetes" in missing_unique:
            recommendations.append("Mencione implantação e sustentação de contêineres e microsserviços em nuvem.")
        if "Ci/Cd" in missing_unique or "Github Actions" in missing_unique:
            recommendations.append("Enfatize automação de rotinas operacionais e pipelines de CI/CD para atualização de infraestrutura.")
        if not recommendations:
            recommendations.append("Seu perfil possui excelente cobertura dos requisitos técnicos desta vaga!")

        # Gera Bullet Points prontos para uso em inglês
        tailored_bullets = self._generate_tailored_bullets(missing_unique, matched_unique)

        return {
            "ats_match_percentage": max(25, min(100, ats_match)),
            "matched_keywords": matched_unique,
            "missing_keywords": missing_unique,
            "key_recommendations": recommendations,
            "tailored_experience_bullets": tailored_bullets
        }

    def _generate_tailored_bullets(self, missing_keywords: List[str], matched_keywords: List[str]) -> List[str]:
        """Gera bullet points profissionais em inglês adaptados para preencher lacunas de ATS."""
        bullets = []

        # Bullet 1: Foco em Azure & Infraestrutura
        bullets.append(
            "Designed, provisioned, and maintained resilient Microsoft Azure infrastructure environments (AZ-104 certified), "
            "enforcing zero-trust network security, RBAC policies, and automated monitoring."
        )

        # Bullet 2: Foco em Automação & Scripting / IaC
        if any(k.lower() in ["terraform", "ansible", "bicep", "ci/cd", "github actions"] for k in missing_keywords + matched_keywords):
            bullets.append(
                "Streamlined operational workflows and deployment consistency by leveraging automation scripts (Python, Bash, PowerShell) "
                "and Infrastructure as Code (IaC) principles to minimize downtime and eliminate manual drift."
            )
        else:
            bullets.append(
                "Automated system maintenance routines and security patching across multi-vendor Linux and Windows Server environments "
                "using modular Python and Shell scripts."
            )

        # Bullet 3: Foco em Segurança & Confiabilidade (SRE)
        bullets.append(
            "Enhanced operational reliability and observability through proactive monitoring (Zabbix, Datadog), "
            "incident response management, and enterprise firewall governance (Fortigate, pfSense)."
        )

        return bullets
