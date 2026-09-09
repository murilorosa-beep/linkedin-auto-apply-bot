"""
Módulo de resolução inteligente de perguntas de candidatura (Easy Apply).
Combina regras determinísticas multilíngues (Português, Inglês, Espanhol, Francês, Alemão),
cobertura completa de dados do CV real do candidato (Murilo Martins) e fallback para IA/heurísticas seguras.
"""

import os
import re
import yaml
from typing import List, Optional, Dict, Any


class QuestionSolver:
    def __init__(self, profile_path: str = "config/profile.yaml", config_path: str = "config/config.yaml"):
        self.profile = self._load_yaml(profile_path)
        self.config = self._load_yaml(config_path)
        self.ai_provider = self.config.get("ai", {}).get("provider", "rules_only")
        self.ai_model = self.config.get("ai", {}).get("model", "gemini-1.5-flash")
        
        # Carregar texto extraído do currículo PDF se disponível
        try:
            from utils.profile_manager import extract_cv_text
            self.cv_text = extract_cv_text()
        except Exception:
            self.cv_text = ""

    def _load_yaml(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def answer_question(
        self,
        question_text: str,
        field_type: str,  # 'text', 'number', 'radio', 'select', 'textarea'
        options: Optional[List[str]] = None
    ) -> str:
        """
        Resolve uma pergunta do formulário do LinkedIn em múltiplos idiomas (EN, PT, ES, FR, DE).
        Prioriza os dados reais do currículo e perfil. Se não encontrar nas regras, usa heurística inteligente ou LLM.
        """
        options = options or []
        normalized_q = question_text.lower().strip()

        # Detectar se o tipo é numérico (anos de experiência, salários, quantidades)
        if field_type in ("text", ""):
            is_numeric = (
                any(w in normalized_q for w in [
                    "how many years", "years of", "years with", "years working", "years experience",
                    "quantos anos", "anos de experiência", "tempo de experiência", "anos com",
                    "cuántos años", "años de experiencia", "tiempo de experiencia", "años con",
                    "combien d'années", "années d'expérience", "années avec", "d'expérience",
                    "wie viele jahre", "jahre erfahrung", "berufserfahrung in"
                ])
                or (
                    any(w in normalized_q for w in ["years", "anos", "años", "années", "jahre"])
                    and not any(w in normalized_q for w in [
                        "describe", "explain", "why", "tell us", "summarize",
                        "descreva", "explique", "conte", "cuéntanos", "parlez", "décrivez"
                    ])
                )
            )
            if is_numeric:
                field_type = "number"

        # 1. Tentar resolver por Regras Determinísticas Multilíngues
        rule_answer = self._solve_by_rules(normalized_q, field_type, options)
        if rule_answer is not None:
            return str(rule_answer)

        # 2. Se for pergunta de opções (Radio / Select) e não mapeada, usar heurística avançada
        if options and field_type in ("radio", "select"):
            matched_option = self._match_options_heuristic(normalized_q, options)
            if matched_option:
                return matched_option

        # 3. Se for campo dissertativo (textarea), gerar resposta técnica contextual e personalizada
        if field_type == "textarea":
            smart_text = self._generate_smart_textarea_response(question_text)
            if smart_text:
                return smart_text

        # 4. Fallback para LLM se configurado (Gemini / OpenAI / Ollama)
        if self.ai_provider != "rules_only":
            llm_ans = self._solve_by_llm(question_text, field_type, options)
            if llm_ans:
                return llm_ans

        # 5. Fallback padrão seguro baseado no tipo de campo e perfil
        return self._default_fallback(field_type, options)

    def _solve_by_rules(self, q: str, field_type: str, options: List[str]) -> Optional[str]:
        """Tenta responder baseando-se nos dados reais do perfil e padrões do LinkedIn em múltiplos idiomas."""
        # Se for campo dissertativo (textarea), direcionar imediatamente para o gerador de texto contextual
        if field_type == "textarea":
            return self._generate_smart_textarea_response(q)

        skills = self.profile.get("skills_experience_years", {})
        work_auth = self.profile.get("work_authorization", {})
        personal = self.profile.get("personal", {})
        links = self.profile.get("links", {})
        edu = self.profile.get("education", {})

        # =========================================================================
        # 1. LINKEDIN URL & LINKS (Prioridade Máxima APENAS para campos de links / não-numéricos)
        # =========================================================================
        is_numeric_question = (
            field_type == "number"
            or any(w in q for w in [
                "how many years", "years of", "years with", "years working", "years experience", "years do you have",
                "quantos anos", "anos de experiência", "anos de experiencia", "tempo de experiência",
                "cuántos años", "años de experiencia", "cuantos anos", "tiempo de experiencia",
                "combien d'années", "années d'expérience",
                "wie viele jahre", "jahre erfahrung"
            ])
            or (any(w in q for w in ["years", "anos", "años", "années", "jahre"]) and any(w in q for w in ["experience", "experiência", "experiencia", "how many", "quantos", "cuántos", "combien"]))
        )

        if not is_numeric_question:
            is_linkedin_req = (
                any(term in q for term in [
                    "perfil do linkedin", "link do linkedin", "url do linkedin", "perfil no linkedin",
                    "link no linkedin", "url no linkedin", "perfil de linkedin", "enlace de linkedin",
                    "url de linkedin", "profil linkedin", "lien linkedin", "url linkedin",
                    "linkedin profil", "linkedin link", "linkedin url", "linkedin profile",
                    "linkedin account", "perfil linkedin", "cuenta de linkedin"
                ])
                or (
                    "linkedin" in q
                    and any(w in q for w in ["url", "link", "profile", "perfil", "enlace", "lien", "cuenta", "compte", "site"])
                )
                or q.strip().rstrip(":*").strip() in ["linkedin", "perfil do linkedin", "perfil linkedin"]
            )
            if is_linkedin_req:
                return links.get("linkedin", "https://www.linkedin.com/in/murilo-martins-0b9938186")

            if any(term in q for term in [
                "github profile", "github link", "github url", "link do github", "perfil do github",
                "enlace de github", "lien github"
            ]) or q.strip().rstrip(":*").strip() in ["github", "git hub"]:
                return links.get("github", "https://github.com/murilomartins")

            if any(term in q for term in ["multicloud", "multi-cloud", "disaster recovery", "backup architecture", "dr project", "projeto de backup"]):
                return links.get("portfolio_dr", "https://github.com/murilorosa-beep/secure-multicloud-backup-dr")

            if (
                re.search(r"\b(portfolio|portfólio|website|web site|sitio web|site web|personal site|webseite|projects|projetos|proyectos)\b", q)
                or any(term in q for term in ["link do portfólio", "link do portfolio", "link do site", "link dos projetos", "enlace al sitio", "lien du site"])
            ):
                return links.get("portfolio", "https://github.com/murilorosa-beep/netvision")

        # =========================================================================
        # 2. DADOS PESSOAIS & CONTATO (EN, PT, ES, FR, DE)
        # =========================================================================
        # Primeiro Nome
        if any(term in q for term in ["first name", "given name", "forename", "primeiro nome", "primer nombre", "prénom", "vorname"]):
            return personal.get("first_name", "Murilo")

        # Sobrenome
        if (
            re.search(r"\b(last name|surname|family name|sobrenome|apellido|nachname)\b", q)
            or re.search(r"\bnom\b", q)
            or any(term in q for term in ["nom de famille", "segundo nombre", "primer apellido"])
        ):
            return personal.get("last_name", "Martins")

        # Nome Completo
        if any(term in q for term in ["full name", "nome completo", "nombre completo", "nom complet", "vollständiger name"]) or q == "name":
            return personal.get("full_name", "Murilo Martins")

        # E-mail
        if any(term in q for term in ["email", "e-mail", "courriel", "correo electrónico", "correo", "e-mail-adresse"]):
            return personal.get("email", "murilo.gmartins@outlook.com")

        # Telefone / Celular
        if any(term in q for term in [
            "phone", "mobile", "cell", "telephone", "phoneNumber",
            "telefone", "celular", "número de telefone",
            "teléfono", "móvil", "número de teléfono",
            "téléphone", "portable", "numéro de téléphone",
            "telefon", "telefonnummer", "handy", "mobilnummer"
        ]):
            return personal.get("phone_national", "11996697230")

        # Cidade
        if any(term in q for term in ["city", "cidade", "ciudad", "ville", "stadt", "municipality", "município"]):
            return personal.get("city", "Jundiaí")

        # Estado / Província
        if (
            any(term in q for term in ["province", "provincia", "région", "département", "bundesland", "uf"])
            or (
                re.search(r"\b(state|estado)\b", q)
                and not any(u in q for u in ["united states", "estados unidos", "états-unis", "autorizado", "authorized"])
            )
        ):
            return personal.get("state", "São Paulo")

        # Código Postal / CEP / ZIP
        if any(term in q for term in ["postal code", "zip code", "zip", "código postal", "cep", "code postal", "postleitzahl", "plz"]):
            return personal.get("postal_code", "13200-000")

        # País de residência
        if any(term in q for term in [
            "country", "country of residence", "residence country",
            "país", "país de residência", "pais",
            "país de residencia",
            "pays", "pays de résidence",
            "land", "wohnsitzland"
        ]):
            if options:
                opt = self._select_best_option("Brazil", options) or self._select_best_option("Brasil", options)
                if opt: return opt
            return personal.get("country", "Brazil")

        # Endereço
        if any(term in q for term in ["address", "street", "endereço", "dirección", "adresse"]):
            return personal.get("address", "Jundiaí, São Paulo, Brazil")

        # =========================================================================
        # 3. PRETENSÃO SALARIAL & COMPENSAÇÃO (BRL para Brasil, USD para EUA, EUR para Espanha)
        # =========================================================================
        if any(term in q for term in [
            "salary", "salario", "salário", "compensation", "rate", "remuneration", "desired pay", "pay rate",
            "pretensão salarial", "pretensao", "remuneração", "valor hora", "quanto você quer ganhar",
            "expectativa salarial", "salario deseado", "tarifa horaria", "retribución", "sueldo",
            "prétention salariale", "salaire souhaité", "tarif horaire",
            "gehaltsvorstellung", "wunschgehalt", "stundensatz"
        ]):
            # 3.1 Mercado Brasileiro (Reais / R$ / Mensal / Pretensão em Português)
            is_brl = (
                any(term in q for term in ["real", "reais", "brl", "r$", "brasil", "brazil", "mensal", "mês", "mes", "clt", "pj"])
                or any(term in q for term in ["pretensão salarial", "expectativa salarial", "pretensao", "valor hora"])
            )
            if is_brl:
                # Se perguntar valor por hora
                if any(term in q for term in ["hour", "hourly", "hora"]):
                    brl_hourly = str(work_auth.get("desired_hourly_brl", "32"))
                    return self._format_number_or_option(brl_hourly, options) if options else brl_hourly
                # Se perguntar explicitamente anual
                if any(term in q for term in ["annual", "ano", "anual", "year"]):
                    brl_annual = str(work_auth.get("desired_salary_brl_annual", "60000"))
                    return self._format_number_or_option(brl_annual, options) if options else brl_annual
                # Padrão Brasil: Pretensão Mensal (calibrada para no máximo R$ 5.000/mês)
                brl_monthly = str(work_auth.get("desired_salary_brl_monthly", "5000"))
                if options:
                    for opt in options:
                        if "5000" in opt or "5.000" in opt or "4.000" in opt or "até 5" in opt.lower():
                            return opt
                    matched_opt = self._select_best_option(brl_monthly, options)
                    if matched_opt:
                        return matched_opt
                return brl_monthly

            # 3.2 Detectar se pergunta especificamente em Euros (€ / Espanha / Europa)
            if any(term in q for term in ["euro", "euros", "eur", "€", "españa", "spain"]):
                if any(term in q for term in ["hour", "hourly", "hora", "heure", "stunde"]):
                    return str(work_auth.get("desired_hourly_eur", "30"))
                return str(work_auth.get("desired_salary_eur_annual", "45000"))

            # 3.3 Padrão USD (EUA / Internacional)
            if any(term in q for term in ["hour", "hourly", "hora", "heure", "stunde"]):
                return str(work_auth.get("desired_hourly_usd", "40"))
            return str(work_auth.get("desired_salary_usd_annual", "75000"))

        # =========================================================================
        # 4. AUTORIZAÇÃO DE TRABALHO, VISTO, DNI/NIE & SPONSORSHIP (EUA, Espanha, UE)
        # =========================================================================
        # DNI / NIE na Espanha (Documentação espanhola)
        if any(term in q for term in [
            "nie", "dni", "nif", "dispones de nie", "tienes nie o dni", "cuenta con nie",
            "documento de identidad español", "tarjeta de residencia", "permiso nie"
        ]):
            if options:
                for opt_cand in ["en trámite", "en tramite", "yes", "sí", "si", "no"]:
                    matched = self._select_best_option(opt_cand, options)
                    if matched:
                        return matched
            return work_auth.get("nie_dni_status", "En trámite / Contrato B2B Internacional")

        # Autorização na Espanha / União Europeia
        if any(term in q for term in [
            "authorized to work in spain", "autorizado para trabajar en españa", "permiso de trabajo en españa",
            "cuenta con permiso de trabajo en españa", "tienes permiso de trabajo en españa", "dispones de permiso de trabajo en españa",
            "derecho a trabajar en españa", "autorización para trabajar en españa", "residencia en españa", "resides en españa",
            "authorized to work in the european union", "authorized to work in the eu", "authorized to work in europe",
            "autorizado a trabalhar na união europeia", "autorizado para trabajar en la unión europea",
            "autorisé à travailler dans l'union européenne"
        ]):
            ans = work_auth.get("authorized_in_spain", work_auth.get("authorized_in_eu", "Yes"))
            return self._select_best_option(ans, options) if options else ans

        # Autorização nos EUA
        if any(term in q for term in [
            "authorized to work in the united states", "legally authorized to work in the us",
            "authorized to work in the u.s.", "legally authorized to work in the united states",
            "autorizado a trabalhar nos estados unidos", "autorizado para trabajar en estados unidos",
            "autorisé à travailler aux états-unis", "arbeitserlaubnis in den usa"
        ]):
            ans = work_auth.get("authorized_in_us", "Yes")
            return self._select_best_option(ans, options) if options else ans

        # Autorização no Brasil
        if any(term in q for term in [
            "authorized to work in brazil", "autorizado a trabalhar no brasil",
            "residente no brasil", "reside en brasil"
        ]):
            return self._select_best_option("Yes", options) if options else "Yes"

        # Necessidade de Patrocínio / Visa Sponsorship
        # Para trabalho remoto internacional PJ (B2B Contractor / Autónomo Espanha / W-8BEN), responde NÃO
        if any(term in q for term in [
            "sponsorship", "require sponsorship", "future sponsorship", "need sponsorship",
            "visa sponsorship", "work visa",
            "patrocínio de visto", "precisa de patrocínio", "necessita de patrocínio",
            "patrocinio de visado", "necesita patrocinio", "requiere visado", "visa de trabajo",
            "parrainage de visa", "besoin d'un parrainage",
            "visumsponsoring", "sponsoring erforderlich"
        ]):
            ans = work_auth.get("requires_sponsorship", "No")
            return self._select_best_option(ans, options) if options else ans

        # Modelo Híbrido & Presença no Escritório (São Paulo, Campinas, Jundiaí e região)
        if any(term in q for term in [
            "híbrido", "hibrido", "hybrid", "modelo híbrido", "trabalho híbrido",
            "dias presenciais", "dias no escritório", "comparecer ao escritório",
            "atuação híbrida", "vaga híbrida", "presencialmente", "acesso a são paulo",
            "região de são paulo", "fácil acesso a", "jundiaí", "campinas"
        ]):
            ans = work_auth.get("comfortable_with_hybrid", "Yes")
            return self._select_best_option(ans, options) if options else ans

        # Modalidade Contrato Remoto / Contractor / B2B / Autónomo Espanha / Freelance
        if any(term in q for term in [
            "contractor", "b2b", "freelance", "w-8ben", "independent contractor",
            "prestador de serviços", "autónomo", "autonomo", "contrato mercantil", "facturar", "facturación",
            "contratista", "prestataire", "freiberufler"
        ]):
            ans = work_auth.get("open_to_contractor_b2b", "Yes")
            return self._select_best_option(ans, options) if options else ans

        # Regime de Contratação Brasil (CLT / PJ / Ambos)
        if any(term in q for term in [
            "clt ou pj", "pj ou clt", "regime de contratação", "modelo de contratação", "tipo de contratação",
            "preferência clt", "preferência pj", "aceita pj", "aceita clt"
        ]):
            if options:
                for opt in options:
                    if any(t in opt.lower() for t in ["ambos", "flexível", "flexivel", "clt ou pj", "pj ou clt", "tanto faz", "sim", "yes"]):
                        return opt
                # Se tiver só CLT ou PJ separados
                clt_opt = self._select_best_option("CLT", options)
                if clt_opt: return clt_opt
            return work_auth.get("preferred_contract_type", "CLT ou PJ (Flexível)")

        # CNPJ / Pessoa Jurídica / Emissão de NF
        if any(term in q for term in [
            "cnpj", "pessoa jurídica", "empresa aberta", "emissão de nota fiscal", "emite nf", "emite nota"
        ]):
            ans = work_auth.get("has_cnpj", "Yes")
            return self._select_best_option(ans, options) if options else ans

        # Confortável com trabalho 100% remoto
        if any(term in q for term in [
            "comfortable working remotely", "remote position", "work remotely",
            "telecommute", "100% remote", "fully remote",
            "trabalho remoto", "vaga remota", "100% remoto",
            "trabajo remoto", "teletrabajo", "100% a distancia",
            "télétravail", "poste à distance", "100% à distance",
            "remote arbeiten", "homeoffice"
        ]):
            ans = work_auth.get("comfortable_with_remote", "Yes")
            return self._select_best_option(ans, options) if options else ans

        # Disposição para Relocalização / Mudança Presencial
        if any(term in q for term in [
            "willing to relocate", "relocation",
            "disposição para mudar", "mudança de cidade", "deslocamento diário",
            "dispuesto a reubicarse", "traslado",
            "prêt à déménager", "relocalisation",
            "umzugsbereit", "bereitschaft zum umzug"
        ]):
            # Para vagas internacionais, o candidato tem abertura total para relocação
            if any(term in q for term in ["relocate", "relocation", "reubicarse", "déménager"]):
                return self._select_best_option("Yes", options) if options else "Yes"
            ans = work_auth.get("willing_to_relocate", "No")
            return self._select_best_option(ans, options) if options else ans

        # Fuso horário e overlap de horários
        if any(term in q for term in [
            "timezone", "time zone", "eastern time", "pacific time", "central time", "hours overlap",
            "fuso horário", "diferença de horário", "huso horario", "fuseau horaire", "zeitzone"
        ]) or re.search(r"\b(est|pst|cst|et|pt)\b", q):
            return self._select_best_option("Yes", options) if options else "Yes"

        # =========================================================================
        # 5. IDIOMAS (Inglês, Português, Espanhol, Francês)
        # =========================================================================
        # Inglês
        if any(term in q for term in ["english", "inglês", "ingles", "inglés", "anglais", "englisch"]):
            if any(term in q for term in [
                "level", "proficiency", "fluent", "speak", "scale", "proficient",
                "nível", "fluência", "fala", "habla", "maîtrise", "kenntnisse"
            ]):
                for fl in ["fluent", "fluente", "courant", "fließend", "professional", "profesional", "advanced", "avançado", "b2"]:
                    opt = self._select_best_option(fl, options)
                    if opt: return opt
                return "Fluent"

        # Português
        if any(term in q for term in ["portuguese", "português", "portugues", "portugués", "portugais"]):
            for nat in ["native", "nativo", "natif", "muttersprache", "fluent", "fluente"]:
                opt = self._select_best_option(nat, options)
                if opt: return opt
            return "Native"

        # Espanhol
        if any(term in q for term in ["spanish", "espanhol", "español", "espanol", "castellano", "espagnol", "spanisch"]):
            for med in [
                "professional", "profesional", "fluent", "fluido", "avanzado", "advanced",
                "b2", "c1", "c2", "intermediate", "intermediário", "intermedio", "yes", "sim", "sí", "si"
            ]:
                opt = self._select_best_option(med, options)
                if opt: return opt
            return "Professional"

        # Francês
        if any(term in q for term in ["french", "francês", "frances", "français", "französisch"]):
            for med in ["intermediate", "intermédiaire", "basic", "básico", "yes", "sim", "oui"]:
                opt = self._select_best_option(med, options)
                if opt: return opt
            return "Intermediate"

        # =========================================================================
        # 6. DISPONIBILIDADE / AVISO PRÉVIO / INCORPORACIÓN (Notice Period)
        # =========================================================================
        if any(term in q for term in [
            "notice period", "start date", "how soon", "when can you start", "availability",
            "aviso prévio", "quando pode começar", "disponibilidade para início", "disponibilidade",
            "período de preaviso", "cuándo puede empezar", "incorporación", "incorporacion", "cuándo te podrías incorporar",
            "préavis", "date de début", "quand pouvez-vous commencer",
            "kündigungsfrist", "startdatum", "wann können sie anfangen", "verfügbarkeit"
        ]):
            for imm in ["inmediata", "inmediato", "immediate", "imediato", "immédiat", "sofort", "2 weeks", "2 semanas", "1 month", "1 mês"]:
                opt = self._select_best_option(imm, options)
                if opt: return opt
            return "Immediate"

        # =========================================================================
        # 7. CERTIFICAÇÕES OFICIAIS (AZ-104, AZ-900, Google Cybersecurity, Linux)
        # =========================================================================
        if any(term in q for term in [
            "az-104", "az104", "az-900", "az900", "azure administrator associate",
            "microsoft certified", "azure certification", "cloud certification",
            "google cybersecurity", "solyd pentest", "linux administrator",
            "certificação azure", "certificación azure", "certificações", "certificaciones",
            "hold any certification", "possui certificação", "tienes alguna certificación",
            "are you certified", "está certificado", "você é certificado"
        ]):
            if options:
                for aff in ["yes", "sim", "sí", "si", "oui", "ja", "true"]:
                    opt = self._select_best_option(aff, options)
                    if opt: return opt
            return work_auth.get("certifications_summary", "Microsoft Certified: Azure Administrator Associate (AZ-104), Azure Fundamentals (AZ-900), Google Cybersecurity Certificate, Linux Administrator")

        # =========================================================================
        # 8. ANOS DE EXPERIÊNCIA TOTAL / GERAL EM TI (5 anos de carreira comprovada)
        # =========================================================================
        is_total_exp_q = (
            any(term in q for term in [
                "total years", "total experience", "overall experience", "overall work",
                "years in it", "years of it", "it experience", "career experience",
                "professional experience", "years in the industry", "years in tech",
                "experiência total", "experiencia total", "anos totais", "anos de experiência profissional",
                "tempo de experiência em ti", "anos de ti", "tempo de ti", "anos de carreira", "anos no mercado",
                "años de experiencia en total", "experiencia general", "años totales"
            ])
            or (
                ("total" in q or "overall" in q or "geral" in q)
                and any(w in q for w in ["year", "years", "anos", "años", "experiência", "experiencia", "experience"])
            )
        )
        if is_total_exp_q:
            total_yrs = skills.get("total_experience", 5)
            return self._format_number_or_option(total_yrs, options)

        # =========================================================================
        # 9. ANOS DE EXPERIÊNCIA COM TECNOLOGIAS ESPECÍFICAS
        # =========================================================================
        is_descriptive = (
            field_type == "textarea"
            or any(w in q for w in [
                "describe", "explain", "tell us", "elaborate", "why", "summarize",
                "descreva", "explique", "conte", "fale sobre", "fale de", "cuéntanos", "describa", "explica"
            ])
        )
        if not is_descriptive and (is_numeric_question or field_type == "number" or any(w in q for w in ["years", "anos", "años", "années", "jahre", "experience", "experiência", "experiencia"])):
            # Caso especial: Site Reliability Engineering / SRE
            if any(term in q for term in ["site reliability", "site reliability engineering", "sre"]):
                sre_years = skills.get("site reliability engineering", skills.get("sre", skills.get("infrastructure", 4)))
                return self._format_number_or_option(sre_years, options)

            # Ordenar habilidades por comprimento decrescente para priorizar termos compostos (ex: active directory antes de directory)
            sorted_skills = sorted(
                [(s, y) for s, y in skills.items() if s not in ["default", "total_experience", "total_it_experience"]],
                key=lambda item: len(str(item[0])),
                reverse=True
            )
            for skill, years in sorted_skills:
                clean_skill = str(skill).lower().replace("_", " ")
                pattern = r"\b" + re.escape(clean_skill) + r"\b"
                if re.search(pattern, q):
                    return self._format_number_or_option(years, options)

            # Se for campo numérico e não encontrou tecnologia específica, retorna o default realista (3 anos)
            if field_type == "number" or is_numeric_question:
                default_years = skills.get("default", 3)
                return self._format_number_or_option(default_years, options)

        # =========================================================================
        # 8. FORMAÇÃO ACADÊMICA / ESCOLARIDADE (Degrees)
        # =========================================================================
        if any(term in q for term in [
            "degree", "education", "bachelor", "diploma", "university", "college",
            "escolaridade", "grau de instrução", "formação", "graduação", "bacharelado", "ensino superior",
            "nivel de estudios", "título", "licenciatura", "grado",
            "diplôme", "niveau d'études", "licence", "bac+",
            "abschluss", "studienabschluss", "hochschulabschluss"
        ]):
            if options:
                for deg in [
                    "bachelor's degree", "bachelor", "bacharelado", "graduação", "licenciatura",
                    "postgraduate", "pós-graduação", "bac+3", "bac+5", "licence", "master", "yes", "sim", "oui"
                ]:
                    opt = self._select_best_option(deg, options)
                    if opt: return opt
            return "Bachelor's Degree"

        # =========================================================================
        # 9. CARTEIRA DE MOTORISTA / HABILITAÇÃO
        # =========================================================================
        if any(term in q for term in [
            "driver's license", "driving licence", "driver license",
            "carteira de motorista", "cnh", "habilitação",
            "licencia de conducir", "carnet de conducir",
            "permis de conduire", "führerschein"
        ]):
            ans = work_auth.get("has_driver_license", "Yes")
            return self._select_best_option(ans, options) if options else ans

        # =========================================================================
        # 10. EEO / DIVERSIDADE / DECLARAÇÕES LEGAIS (EN, PT, ES, FR)
        # =========================================================================
        # Gênero
        if any(term in q for term in ["gender", "sexo", "genre", "geschlecht"]):
            for g in ["male", "masculino", "homme", "männlich", "decline to state", "prefiro não informar"]:
                opt = self._select_best_option(g, options)
                if opt: return opt

        # Raça / Etnia
        if any(term in q for term in ["race", "ethnicity", "etnia", "raça", "ethnie"]):
            for decline in [
                "decline to self-identify", "prefer not to say", "do not wish to answer",
                "two or more races", "white", "pardo", "branca", "prefiro não responder"
            ]:
                opt = self._select_best_option(decline, options)
                if opt: return opt

        # Veterano
        if any(term in q for term in ["veteran", "veterano", "vétéran"]):
            for vet in ["i am not a protected veteran", "not a veteran", "não sou veterano", "no", "não", "non", "nein"]:
                opt = self._select_best_option(vet, options)
                if opt: return opt

        # Deficiência
        if any(term in q for term in ["disability", "deficiência", "discapacidad", "handicap", "behinderung"]):
            for dis in [
                "no, i do not have a disability", "no, i don't have a disability",
                "não possuo deficiência", "no tengo discapacidad", "no", "não", "non", "nein"
            ]:
                opt = self._select_best_option(dis, options)
                if opt: return opt

        # Maioridade (18+ anos) e Checagem de Antecedentes
        if any(term in q for term in [
            "18 years", "at least 18", "legal age", "maior de 18", "maior de idade", "majeur",
            "background check", "drug test", "verificação de antecedentes", "vérification", "test de drogas"
        ]):
            return self._select_best_option("Yes", options) if options else "Yes"

        # Acordo de Não-Concorrência / Non-Compete / Restrictive Covenants (Killer Question)
        if any(term in q for term in [
            "non-compete", "non compete", "noncompete", "restrictive covenant", "acordo de não concorrência",
            "não concorrência", "não-concorrência", "nao-concorrencia", "nao concorrencia", "concorrência", "concorrencia",
            "acuerdo de no competencia", "no competencia", "clause de non-concurrence", "competitor",
            "bound by any agreement", "preso a algum acordo"
        ]):
            ans = work_auth.get("non_compete", "No")
            return self._select_best_option(ans, options) if options else ans

        # Passaporte Válido
        if any(term in q for term in ["passport", "passaporte", "pasaporte", "passeport", "reisepass"]):
            ans = work_auth.get("has_passport", "Yes")
            return self._select_best_option(ans, options) if options else ans

        # Home Office, Conexão e Espaço de Trabalho Silencioso
        if any(term in q for term in [
            "quiet workspace", "dedicated workspace", "dedicated office", "home office setup",
            "high-speed internet", "broadband", "fiber optic", "conexão estável", "internet de alta velocidade",
            "espaço silencioso", "fibra óptica", "conexión a internet", "espacio de trabajo"
        ]):
            ans = work_auth.get("reliable_internet", "Yes")
            return self._select_best_option(ans, options) if options else ans

        # Sobreaviso / Plantão / Disponibilidade de Horário
        if any(term in q for term in [
            "on-call", "on call", "plantão", "sobreaviso", "rotatividade", "guardia", "astreinte",
            "shifts", "weekend", "fim de semana", "fines de semana", "after hours", "fora do horário comercial"
        ]):
            ans = work_auth.get("on_call_shifts", "Yes")
            return self._select_best_option(ans, options) if options else ans

        # Termos, Consentimento e Política de Privacidade
        if any(term in q for term in [
            "terms and conditions", "privacy policy", "data privacy", "consent", "termos e condições",
            "política de privacidade", "concorda com", "términos y condiciones", "política de privacidad",
            "autorizo o tratamento", "i agree", "eu concordo"
        ]):
            for agr in ["i agree", "agree", "yes", "sim", "sí", "si", "aceito", "concordo", "j'accepte"]:
                opt = self._select_best_option(agr, options)
                if opt: return opt
            return "Yes"

        # Conflito de Interesses / Ex-Funcionário / Processo Criminal
        if any(term in q for term in [
            "former employee", "previously worked", "currently employed by", "relatives working",
            "ex-funcionário", "já trabalhou nesta", "parentes trabalhando", "ancien employé",
            "convicted", "felony", "criminal record", "fired", "terminated",
            "processo criminal", "demitido por justa causa", "condamné"
        ]):
            return self._select_best_option("No", options) if options else "No"

        return None

    def _match_options_heuristic(self, q: str, options: List[str]) -> Optional[str]:
        """Tenta encontrar uma correspondência segura e inteligente para seleções e radios em múltiplos idiomas."""
        clean_opts = [opt.strip().lower() for opt in options]

        # 1. Se for Yes / No (ou Sim / Não, Oui / Non, Sí / No, Ja / Nein)
        is_binary_choice = (
            any(o in clean_opts for o in ["yes", "sim", "sí", "si", "oui", "ja", "true", "vrai", "agree", "concordo"])
            and any(o in clean_opts for o in ["no", "não", "nao", "non", "nein", "false", "faux", "disagree"])
        )
        if is_binary_choice:
            negative_keywords = [
                # Sponsorship / Visto (elimina se responder Yes em trabalho remoto B2B)
                "sponsorship", "visa", "patrocínio", "patrocinio", "parrainage", "visum",
                "require sponsorship", "need sponsorship", "future sponsorship", "precisa de visto",
                # Histórico / Conflitos / Crime / Não-Concorrência
                "convicted", "felony", "criminal", "terminated", "fired", "former employee",
                "previously worked", "relatives", "conflict", "non-compete", "non compete", "noncompete",
                "crime", "antecedente", "processo", "demitido", "parente",
                "não concorrência", "não-concorrência", "nao-concorrencia", "nao concorrencia", "concorrência", "concorrencia", "competitor",
                # Deficiência
                "disability", "deficiência", "discapacidad", "handicap", "behinderung",
                # Relocalização forçada
                "relocate", "commute", "relocalisation", "mudança presencial"
            ]

            affirmative_keywords = [
                "authorized to work", "legally authorized", "autorizado a trabalhar", "permiso de trabajo",
                "high-speed internet", "dedicated workspace", "reliable internet", "espaço de trabalho",
                "quiet workspace", "background check", "drug test", "18 years", "legal age", "maior de 18",
                "on-call", "plantão", "sobreaviso", "shifts", "weekend", "passport", "passaporte",
                "terms and conditions", "privacy policy", "consent", "termos", "política", "agree",
                "certified", "certification", "az-104", "az-900", "degree", "diploma", "graduação",
                "hybrid", "híbrido", "remoto", "remote", "contractor", "b2b", "w-8ben", "cnpj",
                "comfortable", "willing", "disposto", "confortável"
            ]

            # Se contiver termos claramente negativos/eliminatórios: responder NÃO
            if any(term in q for term in negative_keywords):
                for opt in options:
                    if opt.lower().strip() in ["no", "não", "nao", "non", "nein", "false"]:
                        return opt
                return "No"

            # Se contiver termos claramente afirmativos: responder SIM
            if any(term in q for term in affirmative_keywords):
                for opt in options:
                    if opt.lower().strip() in ["yes", "sim", "sí", "si", "oui", "ja", "true", "vrai", "agree", "concordo", "i agree"]:
                        return opt
                return "Yes"

            # Para todas as demais perguntas sobre competências, habilidades e autorizações:
            for opt in options:
                if opt.lower().strip() in ["yes", "sim", "sí", "si", "oui", "ja", "true", "vrai", "agree", "concordo", "i agree"]:
                    return opt
            return "Yes"

        # 2. Proficiência de idiomas (Buscar Fluent, Nativo, Avançado)
        for pref in [
            "fluent", "fluente", "courant", "fließend",
            "native", "nativo", "natif", "muttersprache",
            "professional", "profesional", "avançado", "advanced", "avancé",
            "b2", "c1", "c2"
        ]:
            for opt in options:
                if pref in opt.lower():
                    return opt

        # 3. Autodeclarações de neutralidade / declínio (EEO)
        for decline in [
            "prefer not to say", "decline to", "not wish to", "choose not",
            "prefiro não responder", "prefiro não informar", "não desejo informar",
            "não sou um veterano", "i am not a protected veteran",
            "não possuo deficiência", "no, i do not have a disability",
            "masculino", "male", "homme"
        ]:
            for opt in options:
                if decline in opt.lower():
                    return opt

        # 4. País de residência / Origem
        for opt in options:
            if "brazil" in opt.lower() or "brasil" in opt.lower():
                return opt

        # 5. Escolaridade
        for edu_opt in ["bachelor", "bacharelado", "licenciatura", "graduação", "degree", "postgraduate", "pós-graduação"]:
            for opt in options:
                if edu_opt in opt.lower():
                    return opt

        # 6. Avaliação em escala (1-5 ou 1-10) -> Escolher alta proficiência (4 ou 5)
        for high_val in ["5", "4", "expert", "especialista", "advanced", "avançado"]:
            for opt in options:
                if opt.strip().lower() == high_val:
                    return opt

        # 7. Se não houver correspondência clara, escolher a primeira opção disponível
        return options[0] if options else None

    def _select_best_option(self, target: str, options: List[str]) -> Optional[str]:
        """Encontra a opção da lista que mais se aproxima do valor desejado."""
        if not options:
            return None
        target_lower = str(target).lower().strip()
        for opt in options:
            if opt.lower().strip() == target_lower:
                return opt
        for opt in options:
            if target_lower in opt.lower() or opt.lower() in target_lower:
                return opt
        return None

    def _format_number_or_option(self, value: Any, options: List[str]) -> str:
        """Formata um número para input numérico ou encontra a opção/faixa ideal nas opções com precisão máxima."""
        if not options:
            return str(value)

        val_int = int(value) if str(value).isdigit() else 3

        # 1. Correspondência exata do número como string (ex: "4" em ["0", "1", "2", "3", "4", "5"])
        for opt in options:
            clean_opt = opt.strip()
            if clean_opt == str(val_int):
                return opt

        # 2. Faixas numéricas explícitas (ex: "3-5", "3 to 5", "entre 3 e 5 anos")
        for opt in options:
            digits = [int(s) for s in re.findall(r"\d+", opt)]
            if len(digits) >= 2 and digits[0] <= val_int <= digits[1]:
                return opt

        # 3. Opções com '+' ou 'mais' (ex: "5+", "4+ years", "5 or more", "mais de 4")
        for opt in options:
            digits = [int(s) for s in re.findall(r"\d+", opt)]
            if len(digits) == 1 and any(p in opt for p in ["+", "more", "mais", "más"]):
                if val_int >= digits[0]:
                    return opt

        # 4. Encontrar a melhor opção numérica que não exceda desnecessariamente
        best_opt = None
        best_diff = 999
        for opt in options:
            digits = [int(s) for s in re.findall(r"\d+", opt)]
            if digits:
                d = digits[0]
                if d <= val_int and (val_int - d) < best_diff:
                    best_diff = val_int - d
                    best_opt = opt

        if best_opt:
            return best_opt

        best = self._select_best_option(str(value), options)
        return best if best else options[0]

    def _generate_smart_textarea_response(self, q: str) -> str:
        """Gera resposta dissertativa contextual, técnica e de alto impacto baseada na pergunta e idioma."""
        q_lower = q.lower()
        if any(w in q_lower for w in ["descreva", "explique", "experiência", "fale", "qual", "quais", "por que", "você", "conte"]):
            lang = "pt"
        elif any(w in q_lower for w in ["describa", "cuéntanos", "experiencia", "por qué", "explica", "cuál", "cuáles"]):
            lang = "es"
        else:
            lang = "en"

        # 1. Perguntas sobre Azure / Cloud / Nuvem / Infraestrutura Cloud
        if any(k in q_lower for k in ["azure", "cloud", "nuvem", "migração", "migracion", "migration", "iaas", "paas"]):
            if lang == "pt":
                return (
                    "Possuo mais de 4 anos de experiência prática em administração e sustentação de ambientes Microsoft Azure, "
                    "sendo certificado AZ-104 (Azure Administrator Associate) e AZ-900. Minha atuação engloba o gerenciamento "
                    "de máquinas virtuais, redes virtuais (VNet), segurança e governança de identidades via Entra ID (Azure AD), "
                    "Storage Accounts e automação de tarefas operacionais com PowerShell e Python, garantindo alta disponibilidade e segurança."
                )
            elif lang == "es":
                return (
                    "Cuento con más de 4 años de experiencia en administración de infraestructura cloud en Microsoft Azure, "
                    "poseyendo las certificaciones oficiales AZ-104 y AZ-900. Tengo sólida trayectoria gestionando máquinas virtuales, "
                    "redes virtuales (VNet), políticas de acceso e identidad con Entra ID/IAM y automatización operativa mediante PowerShell y Python."
                )
            else:
                return (
                    "I bring 4+ years of hands-on experience designing, securing, and operating Microsoft Azure enterprise environments, "
                    "holding the official AZ-104 (Azure Administrator Associate) and AZ-900 certifications. My background includes managing "
                    "Azure VMs, Virtual Networks (VNets), identity and access governance via Entra ID (Azure AD), cloud backups, and task automation "
                    "using PowerShell and Python to achieve 99.9% uptime and robust security compliance."
                )

        # 2. Perguntas sobre Backup / Disaster Recovery / Multi-Cloud / Resiliência Corporativa
        if any(k in q_lower for k in ["disaster recovery", "backup", "dr", "multicloud", "multi-cloud", "rto", "rpo", "resilience", "contingência", "contingencia", "restauração"]):
            if lang == "pt":
                return (
                    "Possuo sólida vivência em estratégias de contingência, backup isolado e Disaster Recovery corporativo. Desenvolvo o projeto "
                    "aberto 'Secure Multi-Cloud Backup & Disaster Recovery Architecture' integrando Microsoft Azure e AWS através de Infraestrutura como Código (Terraform), "
                    "implementando armazenamento imutável com proteção anti-ransomware, controles de privilégio mínimo e automação de rotinas de failover alinhadas a rigorosos RTO/RPO."
                )
            elif lang == "es":
                return (
                    "Cuento con amplia experiencia en continuidad de negocio, copias de seguridad aisladas y Disaster Recovery. Desarrollo el proyecto "
                    "'Secure Multi-Cloud Backup & Disaster Recovery Architecture' integrando Microsoft Azure y AWS mediante Infraestructura como Código (Terraform), "
                    "incorporando almacenamiento inmutable resistente a ransomware y protocolos automatizados de contingencia con estrictos objetivos RTO/RPO."
                )
            else:
                return (
                    "I have extensive hands-on expertise in business continuity, resilient backup architectures, and Disaster Recovery. "
                    "I am the architect of the open-source 'Secure Multi-Cloud Backup & Disaster Recovery' project integrating Microsoft Azure and AWS "
                    "using Infrastructure as Code (Terraform), implementing immutable ransomware-resilient storage tiers, least-privilege security controls, "
                    "and automated failover procedures tailored to enterprise RTO/RPO objectives."
                )

        # 3. Perguntas sobre Redes / Firewalls / Conectividade
        if any(k in q_lower for k in ["network", "redes", "firewall", "cisco", "fortigate", "pfsense", "vpn", "routing", "switching", "vlan", "tcp"]):
            if lang == "pt":
                return (
                    "Tenho sólida formação e vivência prática de 4+ anos em engenharia de redes, graduado em Redes de Computadores. "
                    "Especialista na configuração e sustentação de firewalls corporativos (Fortigate com FSSO, pfSense), segmentação "
                    "de redes com VLANs, VPNs site-to-site e client-to-site (IPsec/OpenVPN), roteamento dinâmico e monitoramento contínuo "
                    "com Zabbix para garantia de integridade e tolerância a falhas."
                )
            elif lang == "es":
                return (
                    "Cuento con más de 4 años de experiencia en ingeniería y administración de redes corporativas. Especialista en "
                    "despliegue de cortafuegos Fortigate (con integración FSSO) y pfSense, segmentación de redes mediante VLANs, túneles VPN "
                    "(IPsec/OpenVPN), switching, enrutamiento y monitorización proactiva con Zabbix para entornos de alta exigencia."
                )
            else:
                return (
                    "I have 4+ years of comprehensive experience in network engineering and infrastructure administration, backed by a "
                    "Bachelor's in Computer Networks. Experienced in deploying enterprise perimeter security (Fortigate with FSSO, pfSense), "
                    "VLAN segmentation, site-to-site and remote access VPNs (IPsec/OpenVPN), TCP/IP routing, and proactive network observability with Zabbix."
                )

        # 3. Perguntas sobre Segurança da Informação / SIEM / Defesa Cibernética
        if any(k in q_lower for k in ["security", "segurança", "seguridad", "siem", "wazuh", "soc", "incident", "vulnerability", "iso 27001", "defender"]):
            if lang == "pt":
                return (
                    "Atuo com foco em segurança cibernética defensiva e conformidade ISO 27001, certificado pela Google Cybersecurity e Solyd Pentest. "
                    "Experiência na implantação e operação de SIEM Wazuh para detecção de ameaças e auditoria de logs, gestão de endpoints "
                    "com Microsoft Defender, resposta a incidentes de segurança e implementação de backups isolados com proteção contra ransomware."
                )
            elif lang == "es":
                return (
                    "Especializado en ciberseguridad defensiva y cumplimiento bajo estándares ISO 27001, con certificación Google Cybersecurity. "
                    "Experiencia contrastada en implementación y análisis de SIEM Wazuh, gestión de endpoints con Microsoft Defender, "
                    "mitigación de incidentes críticos y esquemas de copias de seguridad aisladas resistentes a ransomware."
                )
            else:
                return (
                    "Specialized in defensive cybersecurity and ISO 27001 compliance standards, certified in Google Cybersecurity. "
                    "Proven track record deploying and fine-tuning Wazuh SIEM for continuous threat detection and log analysis, managing endpoint "
                    "protection with Microsoft Defender, executing rapid incident response protocols, and architecting immutable ransomware-resilient backups."
                )

        # 4. Perguntas sobre Automação / Scripting / DevOps
        if any(k in q_lower for k in ["automation", "automação", "automatización", "python", "powershell", "bash", "devops", "script"]):
            if lang == "pt":
                return (
                    "Desenvolvo rotinas de automação com Python, Bash e PowerShell para eliminar tarefas manuais e aumentar a confiabilidade "
                    "operacional. Criador da plataforma NetVision (gerenciamento e monitoramento de endpoints) e experiente na orquestração de "
                    "servidores em Linux/Windows, rotinas automáticas de auditoria, backup e monitoramento contínuo."
                )
            elif lang == "es":
                return (
                    "Desarrollo automatizaciones avanzadas con Python, PowerShell y Bash para estandarizar procesos operativos. Creador del "
                    "proyecto open-source NetVision para monitorización y gestión de endpoints, con experiencia en orquestación de servidores Linux/Windows "
                    "y automatización de tareas de respaldo y auditoría."
                )
            else:
                return (
                    "I leverage Python, PowerShell, and Bash scripting to automate infrastructure provisioning, repetitive sysadmin routines, "
                    "and operational workflows. Creator of NetVision (an open-source endpoint monitoring and inventory platform) with extensive "
                    "experience automating Linux and Windows administration, health-checks, and resilient backup pipelines."
                )

        # 5. Perguntas de Motivação / "Por que contratar você?" / "Why should we hire you?"
        if any(k in q_lower for k in ["why", "hire", "contratar", "motivação", "interest", "interesse", "qualidades", "diferencial"]):
            if lang == "pt":
                return (
                    "Trago mais de 5 anos de sólida trajetória profissional em infraestrutura de TI, redes corporativas e nuvem Microsoft Azure (AZ-104), "
                    "combinando profundo conhecimento técnico prático com capacidade comprovada de resolução ágil de incidentes críticos (N1-N3). "
                    "Sou altamente proativo, com formação superior em Redes e pós-graduação em Cloud Computing, pronto para agregar valor imediato à equipe."
                )
            elif lang == "es":
                return (
                    "Aporto más de 5 años de sólida experiencia profesional en infraestructura tecnológica, redes y cloud Microsoft Azure (AZ-104), "
                    "combinando rigor técnico con capacidad demostrada para resolver incidencias complejas con rapidez y autonomía. Cuento con "
                    "formación universitaria en redes y mentalidad orientada a la estabilidad de los sistemas y la satisfacción del negocio."
                )
            else:
                return (
                    "I offer 5+ years of solid, hands-on enterprise IT experience spanning infrastructure engineering, networking, and Microsoft Azure cloud (AZ-104). "
                    "I combine strong troubleshooting skills across N1-N3 critical incidents with proactive automation and an obsession for system reliability. "
                    "I am prepared to immediately integrate into the team and drive measurable improvements in uptime and security."
                )

        # 6. Resposta Geral Padrão
        if lang == "pt":
            return (
                "Profissional de Cloud & Infraestrutura com 5 anos de experiência prática no mercado, certificado Microsoft Azure Administrator (AZ-104) "
                "e Azure Fundamentals (AZ-900). Especialista em servidores Linux e Windows, redes corporativas, firewalls e cibersegurança."
            )
        elif lang == "es":
            return (
                "Ingeniero de Cloud e Infraestructura con 5 años de experiencia en el sector tecnológico, certificado Microsoft Azure Administrator (AZ-104) "
                "y Azure Fundamentals (AZ-900). Especialista en administración de sistemas Linux/Windows, redes seguras y ciberseguridad corporativa."
            )
        else:
            return self.profile.get("professional_summary", (
                "Cloud & Infrastructure Engineer with 5 years of hands-on experience in infrastructure, "
                "Microsoft Azure cloud environments, network engineering (firewalls, VPNs), and cybersecurity. "
                "Certified Microsoft Azure Administrator (AZ-104) and Azure Fundamentals (AZ-900)."
            ))

    def _solve_by_llm(self, question: str, field_type: str, options: List[str]) -> Optional[str]:
        """Usa LLM alimentado pelo conteúdo real do currículo para responder à pergunta."""
        summary = self.profile.get("professional_summary", "")
        cv_context = f"CANDIDATE'S FULL CURRICULUM VITAE (CV / RESUME):\n{self.cv_text}\n" if self.cv_text else f"PROFILE SUMMARY:\n{summary}\n"

        prompt = (
            f"You are an automated assistant helping candidate Murilo Martins fill out job applications on LinkedIn.\n\n"
            f"{cv_context}\n"
            f"QUESTION TO ANSWER:\n\"{question}\"\n"
            f"FIELD TYPE: {field_type}\n"
        )
        if options:
            prompt += (
                f"ALLOWED OPTIONS: {options}\n"
                f"RULES:\n"
                f"- You MUST select and output EXACTLY one option from the allowed options list based on the candidate's CV.\n"
                f"- If the candidate has any related experience in CV, pick the positive/affirmative option (e.g., 'Yes', 'Fluent', 'Bachelor\'s Degree').\n"
                f"- Output ONLY the option text, nothing else."
            )
        else:
            if field_type == "number":
                prompt += (
                    f"RULES:\n"
                    f"- Provide ONLY a single integer number (e.g. 3, 4, or 5).\n"
                    f"- If years of experience is not explicitly stated in the CV, estimate a reasonable positive number (between 3 and 5) so the application passes.\n"
                    f"- Output ONLY the number, no words."
                )
            else:
                prompt += (
                    f"RULES:\n"
                    f"- Provide a direct, professional answer in English (maximum 1-2 concise sentences).\n"
                    f"- Directly highlight relevant projects, skills, or achievements from the candidate's CV.\n"
                )

        try:
            if self.ai_provider == "gemini":
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model=self.ai_model,
                        contents=prompt
                    )
                    ans = response.text.strip()
                    return self._select_best_option(ans, options) if options else ans

            elif self.ai_provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    from openai import OpenAI
                    client = OpenAI(api_key=api_key)
                    res = client.chat.completions.create(
                        model=self.ai_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2
                    )
                    ans = res.choices[0].message.content.strip()
                    return self._select_best_option(ans, options) if options else ans

            elif self.ai_provider == "ollama":
                import requests
                ollama_url = self.config.get("ai", {}).get("ollama_url", "http://localhost:11434")
                res = requests.post(
                    f"{ollama_url}/api/generate",
                    json={"model": self.ai_model, "prompt": prompt, "stream": False},
                    timeout=10
                )
                if res.status_code == 200:
                    ans = res.json().get("response", "").strip()
                    return self._select_best_option(ans, options) if options else ans
        except Exception:
            pass

        return None

    def _default_fallback(self, field_type: str, options: List[str]) -> str:
        """Valor padrão seguro garantindo compatibilidade de tipos e respostas favoráveis."""
        if options:
            for opt in options:
                if opt.lower().strip() in [
                    "yes", "sim", "sí", "si", "oui", "ja",
                    "agree", "fluent", "bachelor", "bachelor's degree", "graduação"
                ]:
                    return opt
            return options[0]

        if field_type == "number":
            # Número padrão realista de anos de experiência (atendendo ao pedido de preenchimento sem bloqueio)
            return str(self.profile.get("skills_experience_years", {}).get("default", 3))
        elif field_type == "textarea":
            return self._generate_smart_textarea_response("")
        return "Yes"
