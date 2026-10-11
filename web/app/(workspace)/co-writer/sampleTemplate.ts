const FENCE = "```";

export const CO_WRITER_SAMPLE_TEMPLATE = `# Yaxa Co-Writer

> Yaxa's built-in writing canvas for notes, reports, tutorials, and AI-assisted drafts.

### Features

- Support Standard Markdown / CommonMark / GFM for everyday writing
- Real-time preview for headings, tables, code, math, flowchart, and sequence diagrams
- AI editing workflows for rewrite, shorten, and expand
- HTML tag decoding for tags like <sub>, <sup>, <abbr>, and <mark>
- A practical starter draft for Yaxa product docs and learning content

## Headers (Underline)

Yaxa Learning Note
=============

Yaxa Study Outline
-------------

### Characters

----

~~Deprecated behavior~~ <s>Legacy formatting path</s>
*Italic* _Italic_
**Emphasis** __Emphasis__
***Emphasis Italic*** ___Emphasis Italic___

Superscript: X<sup>2</sup>, Subscript: O<sub>2</sub>

**Abbreviation(link HTML abbr tag)**

The <abbr title="Large Language Model">LLM</abbr> layer powers Yaxa while the <abbr title="Retrieval Augmented Generation">RAG</abbr> layer provides grounded knowledge support.

### Blockquotes

> Yaxa helps students turn questions into structured understanding.
>
> "Learn deeply, write clearly.", [Yaxa](#yaxa-co-writer)

### Links

[Yaxa Co-Writer](#yaxa-co-writer "co-writer section")

[Yaxa Learning Note](#yaxa-learning-note)

[DeepTutor Website](https://deeptutor.info)

[Reference link][deeptutor-doc]

[deeptutor-doc]: #yaxa-learning-note

### Code Blocks

#### Inline code

\`deeptutor chat --once "Summarize this section"\`

#### Code Blocks (Indented style)

    from deeptutor.runtime.orchestrator import ChatOrchestrator
    orchestrator = ChatOrchestrator()
    print("Yaxa is ready.")

#### Python

${FENCE}python
from deeptutor.runtime.orchestrator import ChatOrchestrator
from deeptutor.core.context import UnifiedContext


async def run_demo() -> str:
    orchestrator = ChatOrchestrator()
    context = UnifiedContext(
        user_query="Explain Newton's second law",
        capability="chat",
    )
    result = await orchestrator.run(context)
    return result.get("response", "")
${FENCE}

#### JSON config

${FENCE}json
{
  "app_name": "Yaxa",
  "default_capability": "chat",
  "enabled_tools": ["rag", "web_search", "exec", "reason"],
  "ui": {
    "co_writer_template": true
  }
}
${FENCE}

#### HTML code

${FENCE}html
<section class="deeptutor-card">
  <h1>Yaxa</h1>
  <p>Write, revise, and organize learning content with AI.</p>
</section>
${FENCE}

### Images

![](/logo-ver2.png)

> Yaxa brand mark used inside the co-writer template.

### Lists

- Yaxa Chat
- Yaxa Co-Writer
- Yaxa Research

1. Draft a concept note
2. Ask AI to refine it
3. Export the polished markdown

### Tables

Feature       | Description
------------- | -------------
Co-Writer     | Draft and refine Markdown content
Chat          | Ask questions and iterate ideas
Research      | Build structured multi-step reports

| Capability    | Primary Use Case                     |
| ------------- | ------------------------------------ |
| \`chat\`       | General tutoring and guidance        |
| \`deep_solve\` | Structured problem solving           |
| \`deep_question\` | Question generation and validation |

### Markdown extras

- [x] Draft a Yaxa product note
- [x] Add references and structure
- [ ] Polish the final explanation
  - [ ] Check headings
  - [ ] Check citations

### TeX (LaTeX)

$$ E=mc^2 $$

Inline $$E=mc^2$$ appears in physics notes, and Inline $$a^2+b^2=c^2$$ appears in geometry notes.

$$\\sqrt{3x-1}+(1+x)^2$$

$$ \\sin(\\alpha)^{\\theta}=\\sum_{i=0}^{n}(x^i + \\cos(f))$$

### FlowChart

${FENCE}flow
st=>start: Student asks a question
op=>operation: Yaxa analyzes intent
cond=>condition: Need deep workflow?
chat=>operation: Answer with chat capability
solve=>operation: Route to deep solve
e=>end: Return structured response

st->op->cond
cond(no)->chat
cond(yes)->solve
chat->e
solve->e
${FENCE}

### Sequence Diagram

${FENCE}seq
Student->Yaxa: Ask for help
Yaxa->KnowledgeBase: Load context
Note right of Yaxa: Collect memory\\nand relevant knowledge
Yaxa-->Student: Return guided response
Student->>Yaxa: Request rewrite in co-writer
${FENCE}

### End
`;
