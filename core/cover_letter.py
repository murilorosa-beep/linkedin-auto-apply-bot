"""
Módulo de geração dinâmica e contextual de Cartas de Apresentação (Cover Letters).
Adapta o texto da carta aos requisitos específicos de cada vaga com dados 100% reais do CV do Murilo Martins.
"""

import os
from typing import Dict, Any, Optional


class CoverLetterGenerator:
    def __init__(self, profile: Dict[str, Any], config: Dict[str, Any]):
        self.profile = profile
        self.config = config
        self.ai_provider = config.get("ai", {}).get("provider", "rules_only")
        self.ai_model = config.get("ai", {}).get("model", "gemini-1.5-flash")
        
        personal = profile.get("personal", {})
        self.candidate_name = personal.get("full_name", "Murilo Martins")
        self.candidate_title = personal.get("headline", "Cloud & Infrastructure Engineer")
        self.email = personal.get("email", "murilo.gmartins@outlook.com")
        self.phone = personal.get("phone_formatted", "+55 11 99669-7230")
        self.linkedin = profile.get("links", {}).get("linkedin", "https://www.linkedin.com/in/murilo-martins-0b9938186")

    def generate_cover_letter(
        self,
        job_title: str,
        company: str,
        job_description: str = "",
        language: str = "en"
    ) -> str:
        """
        Gera uma carta de apresentação em 3 parágrafos concisos e de alto impacto.
        Suporta EN (Inglês), PT (Português), ES (Espanhol) e FR (Francês).
        """
        # Se IA configurada, tentar gerar resposta contextualizada
        if self.ai_provider != "rules_only":
            ai_generated = self._generate_with_ai(job_title, company, job_description, language)
            if ai_generated:
                return ai_generated

        # Fallback para template determinístico de alta conversão
        return self._generate_template(job_title, company, language)

    def _generate_template(self, job_title: str, company: str, language: str) -> str:
        """Gera carta estruturada via template profissional de alta conversão."""
        clean_company = company.strip() if company else "your team"
        clean_title = job_title.strip() if job_title else "Cloud & Infrastructure Engineer"

        if language.lower() in ("pt", "portuguese", "português"):
            return (
                f"Prezada equipe de contratação da {clean_company},\n\n"
                f"Escrevo com grande entusiasmo para manifestar meu interesse na posição de {clean_title}. "
                f"Como Engenheiro de Nuvem e Infraestrutura com mais de 4 anos de experiência prática, possuo sólido histórico "
                f"no gerenciamento de ambientes Microsoft Azure, redes corporativas e segurança cibernética, atuando diretamente "
                f"no aumento da resiliência e escalabilidade operacional.\n\n"
                f"Ao longo da minha trajetória, liderei a administração de firewalls corporativos (Fortigate), servidores Linux e Windows, "
                f"além da implantação de monitoramento proativo com Zabbix e Wazuh (SIEM). Possuo certificações oficiais "
                f"Microsoft Certified: Azure Administrator Associate (AZ-104) e Azure Fundamentals (AZ-900), com forte habilidade "
                f"em automatizar rotinas operacionais utilizando Python, Bash e PowerShell.\n\n"
                f"Estou totalmente disponível para atuar remotamente e adoraria ter uma conversa inicial de 15 minutos para demonstrar "
                f"como minhas habilidades podem gerar valor imediato para os desafios da {clean_company}.\n\n"
                f"Atenciosamente,\n"
                f"{self.candidate_name}\n"
                f"{self.linkedin} | {self.phone}"
            )
        elif language.lower() in ("es", "spanish", "español"):
            return (
                f"Estimado equipo de selección de {clean_company},\n\n"
                f"Les escribo con gran entusiasmo para presentar mi candidatura a la posición de {clean_title}. "
                f"Como Ingeniero de Cloud e Infraestructura con más de 4 años de experiencia profesional, cuento con una sólida trayectoria "
                f"gestionando entornos en la nube (Microsoft Azure), redes corporativas y ciberseguridad.\n\n"
                f"Cuento con las certificaciones oficiales Microsoft Azure Administrator Associate (AZ-104) y Azure Fundamentals (AZ-900). "
                f"A lo largo de mi carrera, he administrado servidores Linux y Windows Server, firewalls empresariales (Fortigate, PfSense), "
                f"sistemas de monitorización (Zabbix, Wazuh SIEM) y automatización mediante scripts en Python y Bash.\n\n"
                f"Tengo total disponibilidad para trabajo remoto y me encantaría coordinar una breve conversación de 15 minutos "
                f"para comentar cómo puedo aportar valor técnico inmediato al equipo de {clean_company}.\n\n"
                f"Atentamente,\n"
                f"{self.candidate_name}\n"
                f"{self.linkedin}"
            )
        elif language.lower() in ("fr", "french", "français"):
            return (
                f"Madame, Monsieur,\n\n"
                f"C'est avec grand intérêt que je vous soumets ma candidature pour le poste de {clean_title} chez {clean_company}. "
                f"Ingénieur Cloud et Infrastructure fort de plus de 4 ans d'expérience, je dispose d'une expertise reconnue dans la gestion "
                f"d'environnements Microsoft Azure, l'architecture réseau et la cybersécurité des systèmes distribués.\n\n"
                f"Titulaire des certifications Microsoft Certified: Azure Administrator Associate (AZ-104) et Azure Fundamentals (AZ-900), "
                f"j'ai piloté l'administration de pare-feux Fortigate, de serveurs Linux/Windows et d'outils de surveillance proactive (Wazuh SIEM, Zabbix), "
                f"avec une automatisation poussée via Python et Bash.\n\n"
                f"Disponible immédiatement pour travailler à distance, je serais ravi d'échanger avec vous lors d'un entretien de 15 minutes "
                f"pour vous exposer plus en détail mes réalisations.\n\n"
                f"Cordialement,\n"
                f"{self.candidate_name}\n"
                f"{self.linkedin}"
            )
        else:
            # Padrão: Inglês internacional
            return (
                f"Dear Hiring Team at {clean_company},\n\n"
                f"I am writing to express my strong enthusiasm for the {clean_title} position. "
                f"As a Cloud & Infrastructure Engineer with over 4 years of hands-on experience in cloud systems, enterprise networking, "
                f"and cybersecurity, I have a proven track record of designing, securing, and maintaining scalable and resilient environments.\n\n"
                f"I hold official certifications including Microsoft Certified: Azure Administrator Associate (AZ-104) and Azure Fundamentals (AZ-900). "
                f"My background includes deploying and managing Fortigate firewalls, configuring Linux and Windows Server environments, "
                f"implementing SIEM & monitoring solutions (Wazuh, Zabbix), and automating routine operational workflows with Python and Bash scripts.\n\n"
                f"I am fully available for 100% remote collaboration and would welcome the opportunity to connect for a 15-minute introductory "
                f"conversation to discuss how my skill set aligns with {clean_company}'s engineering objectives.\n\n"
                f"Best regards,\n"
                f"{self.candidate_name}\n"
                f"LinkedIn: {self.linkedin}\n"
                f"Email: {self.email} | Phone: {self.phone}"
            )

    def _generate_with_ai(self, job_title: str, company: str, job_description: str, language: str) -> Optional[str]:
        """Gera carta personalizada via LLM conectando a descrição da vaga com o perfil real."""
        summary = self.profile.get("professional_summary", "")
        prompt = (
            f"Write a concise, high-converting 3-paragraph cover letter for Murilo Martins applying for the job:\n"
            f"Job Title: {job_title}\n"
            f"Company: {company}\n"
            f"Language: {language}\n"
            f"Job Description snippet:\n{job_description[:1000] if job_description else 'N/A'}\n\n"
            f"Candidate Profile:\n{summary}\n"
            f"Key Certifications: Microsoft Certified Azure Administrator (AZ-104), Azure Fundamentals (AZ-900).\n"
            f"Key Skills: Azure, Linux, Fortigate Firewalls, Wazuh SIEM, Networking, Python Automation.\n\n"
            f"Rules:\n"
            f"- Output strictly 3 short paragraphs.\n"
            f"- Tone must be confident, direct, and professional.\n"
            f"- Include contact information and LinkedIn link ({self.linkedin}) at the end.\n"
            f"- Do not include placeholders like '[Insert Date]'."
        )
        try:
            if self.ai_provider == "gemini":
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    res = client.models.generate_content(model=self.ai_model, contents=prompt)
                    return res.text.strip()
            elif self.ai_provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    from openai import OpenAI
                    client = OpenAI(api_key=api_key)
                    res = client.chat.completions.create(
                        model=self.ai_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3
                    )
                    return res.choices[0].message.content.strip()
        except Exception:
            pass
        return None
