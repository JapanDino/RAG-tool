import s from "../styles/portal.module.css";

export type AnswerSection = { heading: string; body: string; bullets: string[]; citations: number[] };
export type AnswerDiagram = {
    title: string;
    nodes: { id: string; label: string }[];
    edges: { source: string; target: string; label: string }[];
    citations: number[];
};
type Citation = { chunk_id: number; document_id: number; title: string };

export default function AnswerLayout({ sections, diagram, citations, onSource, busy }: {
    sections?: AnswerSection[];
    diagram?: AnswerDiagram | null;
    citations: Citation[];
    onSource: (documentId: number, chunkId?: number) => void;
    busy: boolean;
}) {
    function sources(ids: number[]) {
        const docs = citations.filter((c) => ids.includes(c.chunk_id))
            .filter((c, index, all) => all.findIndex((other) => other.document_id === c.document_id) === index);
        return <div className={s.blockSources}>
            {docs.map((c) => <button key={c.document_id} disabled={busy} type="button"
                onClick={() => onSource(c.document_id, c.chunk_id)}>Источник: {c.title}</button>)}
        </div>;
    }
    const labels = new Map(diagram?.nodes.map((node) => [node.id, node.label]));
    return <div className={s.answerLayout}>
        {sections?.map((section, index) => <section key={index} className={s.answerSection}>
            <h3>{section.heading}</h3>
            {section.body && <p>{section.body}</p>}
            {!!section.bullets.length && <ul>{section.bullets.map((item, i) => <li key={i}>{item}</li>)}</ul>}
            {sources(section.citations)}
        </section>)}
        {diagram && <figure className={s.answerDiagram} aria-label={diagram.title}>
            <figcaption><h3>{diagram.title}</h3><p className={s.muted}>Схема по материалам · составлена помощником</p></figcaption>
            <ul className={s.diagramRelations} aria-label="Связи на схеме">
                {diagram.edges.map((edge, i) => <li key={i} className={s.diagramRelation}>
                    <span className={s.diagramNode}>{labels.get(edge.source)}</span>
                    <span className={s.diagramArrow}><span>{edge.label || "связано с"}</span><span aria-hidden="true">→</span></span>
                    <span className={s.diagramNode}>{labels.get(edge.target)}</span>
                </li>)}
            </ul>
            {sources(diagram.citations)}
        </figure>}
    </div>;
}
