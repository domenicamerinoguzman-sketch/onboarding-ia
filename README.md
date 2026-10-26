# Asistente de onboarding con IA · prototipo v1.0

Proyecto de titulación de la Maestría en Inteligencia Artificial Aplicada (UDLA), Grupo 1:
María Doménica Merino Guzmán, Limber Alexander Mosquera Herrera e Ivonne Elizabeth Moscoso Valencia.

*Desarrollo de un sistema inteligente para la automatización del proceso de onboarding mediante
Inteligencia Artificial Generativa y Automatización Inteligente de Procesos en una institución
financiera en Ecuador.*

> **Todos los datos son sintéticos.** Las políticas, preguntas, casos y nombres los redactó el equipo.
> Ninguna cifra de este repositorio mide desempeño en una organización real ni ahorro de tiempo.

![Demo del asistente](docs/img/demo_asistente_responde.png)

---

## 1. Problema y solución

**Problema.** En la institución, el onboarding de nuevos colaboradores lo ejecutan tres analistas de
Talento Humano con actividades mayoritariamente manuales: validación de documentos, contrato,
solicitudes de accesos, coordinación con otras áreas, seguimiento en hojas de control y respuesta a
las dudas del colaborador. La propuesta reporta unas 4 horas por incorporación y entre 30 y 36
ingresos al mes (*dato proporcionado, pendiente de validación*).

**Solución.** Un sistema con dos componentes **separados a propósito**:

| Componente | Tipo | Qué hace | Por qué ese tipo |
|---|---|---|---|
| Asistente de consultas (`src/asistente.py`) | **IA** · RAG | Responde preguntas en lenguaje natural sobre las políticas de inducción, cita la fuente y deriva a Talento Humano lo que no puede responder con confianza | Las preguntas llegan con sinónimos, coloquialismos y erratas que las reglas no cubren |
| Flujos de onboarding (`src/flujos/`) | **Automatización tradicional** · reglas | Planifica 13 tareas por caso en días hábiles, crea tickets, encola notificaciones por plantilla y escala excepciones con su motivo | Las condiciones son explícitas y auditables; usar IA añadiría riesgo sin beneficio |

## 2. Pipeline del asistente

![Arquitectura](docs/img/arquitectura_v1.png)

1. **Guardas de entrada** (`src/guardas.py`). Detectan intentos de inyección de instrucciones y los
   derivan sin consultar al modelo; enmascaran cédulas, correos, teléfonos y tarjetas antes de que
   lleguen al modelo o al registro.
2. **Recuperación híbrida** (`src/recuperadores.py`). BM25 (k1 = 1,2; b = 0,75) sobre texto
   normalizado (sin tildes, sin palabras vacías, raíces Snowball, títulos en el índice), con
   expansión de la consulta por un diccionario de sinónimos (`data/sinonimos.json`) y un componente
   de n-gramas de caracteres (peso 5) que tolera erratas.
3. **Derivación.** Si el puntaje del primer pasaje es menor que 4,563 (umbral en
   `config/modelo_final.json`), la consulta se deriva a Talento Humano.
4. **Generación en modo dual** (`src/generacion.py`).
   - **LLM local** con [Ollama](https://ollama.com) (por defecto `qwen2.5:3b`, temperatura 0) y el
     prompt `prompts/respuesta_rag_v2.txt`, que recibe los 3 pasajes delimitados como datos.
     Los datos no salen del equipo.
   - **Respaldo extractivo**: si Ollama no está disponible, falla o su respuesta no pasa la
     verificación, se devuelven las oraciones más pertinentes del pasaje con la cita.
5. **Verificador de fidelidad.** Una respuesta del LLM solo se entrega si cita un pasaje recuperado y
   todas sus cifras (plazos, montos, horas, porcentajes) aparecen en ese pasaje.
6. **Trazabilidad.** Cada respuesta incluye la versión, los candidatos con su puntaje, los términos
   que más aportaron (descomposición exacta de BM25), las expansiones aplicadas y el modo de
   generación. Con `--registrar`, se guarda un registro mínimo sin la pregunta en claro.

## 3. Requisitos

- Python **3.11 o superior** (probado con 3.11.15 y 3.13.17).
- Dependencias de `requirements.txt` (solo bibliotecas de código abierto):

| Paquete | Versión fijada | Uso |
|---|---|---|
| numpy | 2.4.4 | cálculo |
| scipy | 1.17.1 | McNemar, Wilcoxon |
| scikit-learn | 1.8.0 | TF-IDF, particiones estratificadas |
| nltk | 3.9.1 | raíces Snowball para español (no requiere descargas) |
| matplotlib | 3.10.9 | figuras |

- **Opcional, para la generación con LLM:** Ollama instalado y un modelo descargado
  (≈ 2 GB; funciona en una laptop con 8 GB de RAM, sin GPU):

```bash
ollama pull qwen2.5:3b          # alternativa: ollama pull llama3.2:3b
```

La demo web usa solo la biblioteca estándar: no hay que instalar nada más.

## 4. Ejecución paso a paso

```bash
git clone https://github.com/domenicamerinoguzman-sketch/onboarding-ia.git
cd onboarding-ia
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**a) Reproducir todos los resultados de una vez** (≈ 1 minuto, sin LLM):

```bash
python -m experimentos.reproducir_todo
```

**b) O paso a paso:**

```bash
python -m experimentos.validacion_cruzada     # 1. v0.2: A0–A5, validación cruzada 5×10
python -m experimentos.validacion_v1          # 2. v1.0: ablación A4, B1–B5 (mismas particiones)
python -m experimentos.ajustar_modelo_final   # 3. umbral final -> config/modelo_final.json
python -m experimentos.prueba_final           # 4. conjunto reservado (110 preguntas)
python -m experimentos.robustez               # 5. perturbaciones, guardas y verificador
python -m experimentos.evaluar_generacion     # 6. extremo a extremo (modo extractivo)
python -m experimentos.graficos               # 7. figuras
python -m experimentos.graficos_v1
python -m unittest discover -s tests -t .     # 8. 35 pruebas
```

**c) Usar el asistente:**

```bash
python -m src.asistente "¿Qué día me entregan la laptop?"
python -m src.asistente --modo extractivo "¿Cuánto dura el período de prueba?"
python -m src.asistente --modo llm_local "¿Puedo trabajar desde casa?"     # requiere Ollama
```

**d) Ejecutar los flujos de automatización:**

```bash
python -m src.flujos.orquestador                 # los 3 casos de data/casos_demo.json
python -m src.flujos.orquestador --caso C-DEMO-02 --completo
```

**e) Demo web** (asistente + flujos):

```bash
python -m app.servidor            # http://127.0.0.1:8000
```

**f) Evaluar la generación con el LLM real** (en un equipo con Ollama):

```bash
ollama serve &                                   # si no está corriendo
python -m experimentos.evaluar_generacion --modo llm_local
python -m experimentos.evaluar_generacion --modo llm_local --modelo llama3.2:3b
```

Esto escribe `resultados/v1/generacion_llm_local_<modelo>.json` (exactitud de extremo a extremo,
fidelidad verificada, tasa de descarte, latencia) y una muestra de 30 respuestas para revisión
humana con la rúbrica de `docs/rubrica_revision_humana.md`.

Todos los resultados se regeneran con la semilla `20260928`.

## 5. Estructura

```
app/                demo web (servidor y página)
config/             modelo_final.json (v1.0), modelo_v0.2.json, flujo_onboarding.json
data/               corpus (46 pasajes), preguntas de desarrollo (162), prueba reservada (110),
                    sinónimos, pruebas de seguridad, casos de demostración
docs/               arquitectura, capturas, rúbrica de revisión humana, índice de anexos
experimentos/       validación cruzada, prueba final, robustez, evaluación, figuras
plantillas/         plantillas de notificación de los flujos
prompts/            respuesta_rag_v1.txt (v0.2) y respuesta_rag_v2.txt (v1.0)
resultados/         v0.2 (raíz) y v1.0 (resultados/v1/): métricas JSON, predicciones, figuras
src/                preprocesamiento, sinónimos, recuperadores, evaluación, guardas,
                    generación, asistente, reglas de escalamiento y flujos/
tests/              35 pruebas unitarias y de integración
v0_reglas/          entrega v0.1: baseline de reglas y 80 casos sintéticos
BITACORA.md         decisiones y resultados por versión
CHANGELOG.md        cambios por versión
```

## 6. Metodología de validación

| Conjunto | Preguntas | Uso |
|---|---|---|
| Desarrollo (`data/preguntas_evaluacion.csv`) | 162: 46 directas, 92 parafraseadas, 24 fuera de alcance | Diseño, validación cruzada 5 × 10 y elección del umbral |
| **Reservado** (`data/prueba_reservada.csv`) | 110: 93 parafraseadas, 17 fuera de alcance | **Solo la prueba final.** Se redactó después de congelar el modelo (ver `git log`) |

- **Métrica principal:** exactitud del asistente (responde con el pasaje correcto o deriva cuando la
  pregunta está fuera de alcance). **Métrica de riesgo:** tasa de respuesta errónea (entrega un
  pasaje equivocado o responde algo fuera de las políticas).
- **Sin fuga en la validación cruzada:** umbrales e hiperparámetros se eligen solo con las preguntas
  de entrenamiento de cada pliegue.
- **Incertidumbre:** DE entre pliegues y repeticiones; IC 95 % por bootstrap pareado (5000
  remuestreos); McNemar exacta por repetición.

## 7. Resultados

### 7.1 Validación cruzada sobre desarrollo (media ± DE entre pliegues)

| Variante | Exactitud | Respuesta errónea | Hit@1 | Hit@3 |
|---|---|---|---|---|
| A0 Baseline palabras clave (v0.2) | 0,399 ± 0,059 | 0,475 ± 0,067 | 0,449 | 0,601 |
| A4 BM25 (adoptado en v0.2) | 0,644 ± 0,067 | 0,246 ± 0,071 | 0,739 | 0,848 |
| B1 A4 + sinónimos | 0,807 ± 0,050 | 0,157 ± 0,047 | 0,891 | 0,978 |
| B2 A4 + caracteres | 0,696 ± 0,066 | 0,213 ± 0,058 | 0,746 | 0,870 |
| **B3 Sinónimos + caracteres (adoptado en v1.0)** | **0,831 ± 0,048** | **0,151 ± 0,045** | **0,891** | **0,978** |
| B4 B3 + derivación por cobertura | 0,832 ± 0,051 | 0,140 ± 0,047 | 0,891 | 0,978 |

B3 frente a A4: +0,204 (IC 95 %: 0,136 a 0,272; McNemar p < 0,001 en las 10 repeticiones).
B4 no mejora a B3 (−0,012; IC −0,037 a 0,012): la regla de cobertura eligió `c = 0` en 45 de 50
pliegues, así que se descartó por parsimonia.

> ⚠️ **Estas cifras son optimistas para B1, B3 y B4**: el diccionario de sinónimos se redactó
> analizando los errores de v0.2 sobre estas mismas 162 preguntas.

![Validación v1](resultados/figuras/validacion_v1.png)

### 7.2 Prueba final en el conjunto reservado (umbrales fijos, sin ajuste)

| Sistema | Exactitud [IC 95 %] | Respuesta errónea | Hit@1 | Hit@3 | Parafraseadas | Fuera de alcance |
|---|---|---|---|---|---|---|
| A0 Baseline | 0,509 [0,418; 0,600] | 0,427 | 0,591 | 0,667 | 0,559 | 0,235 |
| A4 BM25 (v0.2) | 0,773 [0,700; 0,845] | 0,173 | 0,785 | 0,935 | 0,774 | **0,765** |
| **v1.0 Final** | **0,773 [0,700; 0,845]** | **0,164** | **0,828** | **0,957** | **0,817** | 0,529 |

- v1.0 frente a A0: +0,264 (IC 0,164 a 0,364; McNemar p < 0,001).
- **v1.0 frente a A4: sin diferencia** (0,000; IC −0,055 a 0,045; 4 aciertos exclusivos de cada uno).
  v1.0 recupera mejor (Hit@1 +0,043; parafraseadas +0,043), pero deriva peor las preguntas fuera de
  alcance (0,529 frente a 0,765): el componente de caracteres sube el puntaje de preguntas ajenas.
- **Conclusión:** la mejora de validación cruzada no se sostuvo con preguntas nuevas. Es la evidencia
  más honesta del proyecto y orienta el trabajo siguiente (derivación como problema propio, sinónimos
  validados por Talento Humano). Ver `BITACORA.md`.

![Prueba reservada](resultados/figuras/prueba_reservada.png)

### 7.3 Robustez y seguridad (`resultados/v1/robustez.json`)

| Perturbación (conjunto reservado) | A4 exactitud | v1.0 exactitud | v1.0 Hit@1 |
|---|---|---|---|
| Limpia | 0,773 | 0,773 | 0,828 |
| Sin tildes / MAYÚSCULAS | 0,773 | 0,773 | 0,828 |
| Saludo y cortesía alrededor | 0,718 | 0,727 | 0,817 |
| Una errata por pregunta (5 semillas) | 0,700 | 0,705 | 0,774 |
| Dos erratas por pregunta (5 semillas) | 0,576 | 0,615 | 0,701 |

- **Inyección de instrucciones:** 12 de 14 ataques bloqueados en la primera ejecución, sin falsos
  positivos en 8 controles. Los 2 fallos (S02, S13) se corrigieron; la cifra posterior (14/14) ya no
  es una estimación independiente.
- **Datos personales:** 6 de 6 casos enmascarados; 0 falsos positivos en 3 controles (extensiones,
  porcentajes).
- **Verificador de fidelidad:** clasifica bien 16 de 16 respuestas construidas (detecta las 8 no
  fieles). No detecta afirmaciones falsas sin cifras; por eso existe la revisión humana.
- **Ruta del LLM:** probada con un servidor Ollama simulado (`tests/test_generacion.py`): respuesta
  fiel entregada, cifra inventada descartada, falta de cita descartada, derivación respetada, error
  con respaldo, inyección y datos personales que no llegan al modelo.

### 7.4 Extremo a extremo y flujos

- **Modo extractivo** (`resultados/v1/generacion_extractivo.json`): exactitud 0,773 en el reservado,
  100 % de respuestas con cita verificada, latencia mediana < 0,01 s.
- **Modo LLM local:** **pendiente de ejecución por el equipo** (sección 4f); el entorno donde se
  construyó v1.0 no tenía acceso para descargar modelos.
- **Flujos:** en los 3 casos de demostración, las actividades manuales pasan de 11–13 (AS-IS) a 3
  (TO-BE): validar documentos, elaborar el contrato (asistida) y asignar el compañero guía. Es un
  **conteo sobre el modelo AS-IS preliminar**, no una medición de tiempo.

## 8. Limitaciones

- Datos sintéticos redactados por el mismo equipo (sesgo de vocabulario); el conjunto reservado
  también lo escribió el equipo, conociendo el corpus.
- La etapa generativa con LLM real no se ha evaluado todavía.
- La derivación de preguntas fuera de alcance sigue siendo débil (0,53 en el reservado).
- Los conectores son simulados; no se ha medido tiempo real ni satisfacción de usuarios.
- El diccionario de sinónimos y el calendario de feriados están pendientes de validación.

## 9. Anexos técnicos

Índice de evidencias y anexos de entregas anteriores: [`docs/ANEXOS.md`](docs/ANEXOS.md).
Decisiones: [`BITACORA.md`](BITACORA.md). Cambios: [`CHANGELOG.md`](CHANGELOG.md).
