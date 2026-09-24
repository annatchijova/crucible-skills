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

Ya existen ocho niveles coherentes: el compilador L1 transforma un corpus real en una Skill IR versionada, con source spans y digest SHA-256 determinista; el auditor L2 consume esa IR, emite findings con evidencia y estado epistémico (CONFIRMED / CANDIDATE / OBSERVATION), sella un AuditArtifact (`crucible-audit/v1`) y documenta cinco checks abstados como limitaciones explícitas. 8 checks están implementados: BROKEN_REFERENCE, SELF_COMPOSITION, COMPOSITION_CYCLE, ORPHAN_SKILL, REQUIREMENT_WITHOUT_CHECK, STRUCTURAL_REDUNDANCY, METHODOLOGICAL_VACUITY (reglas pero sin pasos procedurales ni checks — detecta skills que dicen qué hacer pero nunca cómo), NORMATIVE_CONFLICT (mismo subject, modalidad opuesta — detecta contradicciones dentro y entre skills), SEMANTIC_REDUNDANCY (Jaccard token overlap >= 2/3 con Fraction, sin floats — detecta skills que cubren el mismo ground; capa de confirmación LLM diferida), CONDITIONAL_CONTRADICTION (mismo subject, conditions superpuestas, polaridad efectiva opuesta — detecta reglas que parecen compatibles en general pero conflictúan bajo una condición específica) y SCOPE_TRIGGER_MISMATCH (trigger declarado comparte cero tokens con el contenido de las reglas; 2 findings CANDIDATE en el corpus real, ambos falsos positivos documentados como CANDIDATE con limitación). La IR ahora extrae subjects de reglas, condiciones, triggers y pasos procedurales para soportar estos checks. El grafo L3 extrae aristas tipadas de relaciones desde headings de sección y texto de descripción (sibling of, pairs with, composes with, member of the family, companion to), los clasifica en composition/reinforcement/delegation, detecta hubs y componentes desconectados, y sella un GraphArtifact (`crucible-graph/v1`); el laboratorio L4 siembra 8 clases de defectos contra un fixture conocido-bueno, corre el pipeline completo, y clasifica cada resultado como KILLED / SURVIVED / ABSTAINED con clasificación honesta de survivors (INSUFFICIENT_DETECTOR, INSUFFICIENT_REPRESENTATION, OUT_OF_SCOPE), kill rate 4/6; el diferencial conductual L5 corre el mismo task contra 4 variantes de skill (no-skill, original, mutante, repair), observa 4 propiedades explícitas con un oracle determinista, y sella el reporte (el executor local muestra el diferencial esperado; Nebius/Nemotron BLOCKED sin API key); el workflow de Bob L6 recibe findings de auditoría, propone un repair (rule-based o LLM via Nebius), y Crucible determinísticamente re-audita y acepta o rechaza (finding gone + no new findings + compiles); el loop de repair cerrado L7 integra L6 y L5 en un solo workflow: Bob propone, Crucible re-audita determinísticamente, y si pasa el gate determinista corre un behavioral replay comparando el repair contra el original. Un repair que pasa el determinista pero falla el behavioral es REJECTED con `BEHAVIORAL_REGRESSION`. Bob propone; el property oracle observa; Crucible decide. Y las superficies de presentación L8 integran todo: un generador de reporte compuesto corre el pipeline L1-L7 completo y sella un artifact `crucible-report/v1` con todos los digests; un viewer HTML read-only renderiza cualquier artifact sellado como una página self-contained (sin cómputo, sin `<script>` tags); y un workflow de GitHub Actions corre los tests, genera el reporte, renderiza el HTML, y sube ambos como artifacts. Ningún consumidor tiene lógica de decisión independiente.

## Principio de construcción

El destino es un sistema completo de verificación de metodología. El tiempo decide hasta qué nivel coherente llegamos; no convierte los niveles no alcanzados en prototipos descartables. Cada nivel debe ser útil, compatible con el siguiente y conservar los invariantes anteriores.

## Licencia

Apache-2.0. Ver [`LICENSE`](LICENSE).
