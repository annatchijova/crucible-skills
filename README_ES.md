# Crucible Skills

**Ingeniería de verificación para metodologías de agentes de IA.**

[English](README.md) · **Español** · [Technical README](TECHNICAL.md)

![Logo de Crucible Skills](visual/logo.png)

> **Estado: en progreso — primero el contrato arquitectónico y de evaluación.**

Las skills de agentes son metodología ejecutable: cambian qué detecta, prioriza, verifica y hace un agente de coding. Ya existen herramientas para validar su forma, buscar comportamiento malicioso y medir si un agente rinde mejor con ellas. Falta una pregunta más difícil:

> **¿La metodología es coherente, verificable, componible y realmente vale la pena agregarla al corpus?**

Crucible Skills busca responderla con evidencia estructurada, no con un puntaje opaco.

## Por qué existe ahora

Las Agent Skills se están convirtiendo en infraestructura. NVIDIA ya está construyendo infraestructura seria alrededor de ellas: SkillSpector cubre riesgos de seguridad y supply chain; SkillEvaluator cubre validación, overlap semántico, datasets sintéticos y evaluación live de agentes; y el catálogo NVIDIA agrega Skill Cards, firmas, benchmarks y gates de publicación. Queremos esos controles. CRUCIBLE no existe porque sean insuficientes o irrelevantes, sino porque no agotan la pregunta metodológica.

> **Una skill no necesita ser maliciosa para ser una mala metodología. Puede ser perfectamente benigna y aun así enseñar a un agente a construir mal.**

Ejemplo:

```text
Skill A: reintentar operaciones fallidas hasta tener éxito.
Skill B: las acciones irreversibles deben ser acotadas y revisables.

Ninguna es necesariamente maliciosa por separado.
La composición falla cuando el objetivo del retry es irreversible y no idempotente.
```

CRUCIBLE intenta hacer ese tipo de afirmación inspeccionable, condicional y falsable. Es una capa complementaria de verificación metodológica, no un reemplazo de un security scanner ni de un evaluator conductual. Ver la [frontera competitiva](docs/COMPETITIVE_BOUNDARY.md).

## La idea en un ejemplo

Dos skills pueden parecer razonables por separado y producir una composición incorrecta:

```text
Skill A: reintentar operaciones críticas hasta que tengan éxito.
Skill B: las operaciones irreversibles deben tener efectos acotados y revisables.

Plausibles por separado → composición insegura cuando el retry duplica un efecto irreversible.
```

Crucible extrae reglas declaradas, scopes, triggers, checks, referencias y aristas de composición; después audita contradicciones, verificaciones ausentes, redundancia, provenance rota y resistencia a mutaciones.

## Estado del documento

Esta versión es una adaptación de trabajo en español. La especificación pública y el roadmap canónico están en inglés; el plan operativo en español se mantiene local e ignorado por Git para poder iterarlo durante el hackathon.

Ver el detalle completo en el [Technical README](TECHNICAL.md) y el mapa de construcción en [ROADMAP.md](docs/ROADMAP.md).

## Estado de implementación

Ya existen ocho niveles coherentes: el compilador L1 transforma un corpus real en una Skill IR versionada, con source spans y digest SHA-256 determinista; el auditor L2 consume esa IR, emite findings con evidencia y estado epistémico (CONFIRMED / CANDIDATE / OBSERVATION), sella un AuditArtifact (`crucible-audit/v1`) y documenta 0 checks abstados. 28 checks están implementados: BROKEN_REFERENCE, SELF_COMPOSITION, COMPOSITION_CYCLE, ORPHAN_SKILL, REQUIREMENT_WITHOUT_CHECK, STRUCTURAL_REDUNDANCY, METHODOLOGICAL_VACUITY (reglas pero sin pasos procedurales ni checks), NORMATIVE_CONFLICT (mismo subject, modalidad opuesta), SEMANTIC_REDUNDANCY (Jaccard token overlap >= 2/3 con Fraction, sin floats; capa de confirmación LLM diferida), CONDITIONAL_CONTRADICTION (mismo subject, conditions superpuestas, polaridad efectiva opuesta), SCOPE_TRIGGER_MISMATCH (trigger declarado comparte cero tokens con el contenido de las reglas), DESCRIPTION_BODY_GAP (descripción sustantiva pero cero reglas, checks y pasos procedurales extraíbles; 15 findings CANDIDATE en el corpus real), CHECK_WITHOUT_ORACLE (check sin indicador de verificación extraíble; 16 findings CANDIDATE en el corpus real), CLAIM_WITHOUT_PROVENANCE (regla con claim numérico/referencia a standard sin citación de fuente; 0 findings en el corpus real), UNBOUNDED_RETRY (retry/repeat sin max attempts, timeout, backoff o circuit breaker; 4 findings CANDIDATE en el corpus real), LLM_IN_DECISION_PATH (LLM/model usado para decisión consecuencial sin guard determinista; 0 findings en el corpus real), OVERCLAIM (claim absoluto — always, never, guaranteed, failsafe — sin calificación; 2 findings CANDIDATE en el corpus real), MISSING_FAILURE_MODE (reglas y pasos pero cero mención de failure, error, exception, fallback o recovery; 0 findings en el corpus real), NON_DETERMINISTIC_INSTRUCTION (random, arbitrary, pick any — sin seed o anchor reproducible; 3 findings CANDIDATE en el corpus real), IRREVERSIBLE_WITHOUT_REVIEW (delete, drop, destroy, force-push, truncate, purge — sin review, backup, idempotency o rollback; 18 findings CANDIDATE en el corpus real), SECRET_IN_OUTPUT (secret enviado a log/print/echo/stdout sin redaction/mask/hash/encrypt; 1 finding CANDIDATE en el corpus real), SILENT_FAILURE (error ignored/swallowed/suppressed sin log/report/raise/retry; 0 findings en el corpus real), HARDCODED_CREDENTIAL (secret/password/token hardcoded en código sin env var/vault/KMS; 0 findings en el corpus real), UNBOUNDED_RESOURCE (load all/read all/load into memory sin limit/max/batch/stream/paginate; 0 findings en el corpus real), UNVALIDATED_EXTERNAL_INPUT (user input/request/stdin/argv aceptado sin validate/sanitize/schema/type check; 0 findings en el corpus real), MISSING_TIMEOUT (wait indefinitely/block forever/wait until success sin timeout/deadline/TTL; 0 findings en el corpus real), FLOATING_POINT_IN_DECISION_PATH (float comparado por equality o usado para money sin Fraction/Decimal/integer/epsilon; 0 findings en el corpus real), y UNPINNED_DEPENDENCY (pip/npm/cargo install sin version pin o lock file; 0 findings en el corpus real). La IR extrae subjects de reglas, condiciones, triggers, pasos procedurales, oracle_kind de checks y claims de reglas para soportar estos checks. La capa de confirmación L2.5 toma TODOS los CANDIDATEs del L2 audit y pregunta a un executor (Nemotron vía Nebius, o mock determinista) si cada uno es un defecto real o un falso positivo. La confirmación es un artifact separado (`crucible-confirmation/v1`) con su propio digest SHA-256. El L2 audit artifact NUNCA se modifica — la confirmación es una OBSERVATION, no una promoción a CONFIRMED. Si `NEBIUS_API_KEY` no está set, la confirmación es BLOCKED, no simulada.

## Principio de construcción

El destino es un sistema completo de verificación de metodología. El tiempo decide hasta qué nivel coherente llegamos; no convierte los niveles no alcanzados en prototipos descartables. Cada nivel debe ser útil, compatible con el siguiente y conservar los invariantes anteriores.

## Licencia

Apache-2.0. Ver [`LICENSE`](LICENSE).
