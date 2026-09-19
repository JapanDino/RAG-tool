import { useEffect, useRef, useState } from "react";
import CourseChat, { PortalAPI, ReadingContext } from "./CourseChat";
import MaterialImage, { Illustration } from "./MaterialImage";
import s from "../styles/portal.module.css";

export type MaterialSource = {
    title: string;
    document_id: number;
    published: boolean;
    source_url?: string;
    original_available?: boolean;
    original_mime?: string;
    images?: Illustration[];
    chunks: { id: number; text: string; page?: number }[];
    focusChunk?: number;
    focusPage?: number;
};

export default function MaterialReader({
    source,
    token,
    api,
    scope,
    onSource,
    onClose,
    onDownload,
    allowReview,
    teacher = false,
}: {
    source: MaterialSource;
    token: string;
    api: PortalAPI;
    scope?: string;
    onSource: (id: number, chunk?: number, page?: number) => void;
    onClose: () => void;
    onDownload: () => void;
    allowReview: boolean;
    teacher?: boolean;
}) {
    const [context, setContext] = useState<ReadingContext>({
        document_id: source.document_id,
    });
    const [seed, setSeed] = useState<{ text: string; nonce: number }>();
    const [pdf, setPDF] = useState("");
    const [error, setError] = useState("");
    const text = useRef<HTMLDivElement>(null);
    const focusPage =
        source.focusPage ||
        source.chunks.find((c) => c.id === source.focusChunk)?.page ||
        1;
    useEffect(() => {
        setContext({
            document_id: source.document_id,
            chunk_id: source.focusChunk,
        });
        if (source.focusChunk)
            text.current
                ?.querySelector(`[data-chunk-id="${source.focusChunk}"]`)
                ?.scrollIntoView({ block: "center" });
    }, [source.document_id, source.focusChunk]);
    useEffect(
        () => () => {
            if (pdf) URL.revokeObjectURL(pdf);
        },
        [pdf],
    );
    async function openPDF() {
        setError("");
        if (!navigator.pdfViewerEnabled) {
            setError(
                "В этом браузере нет встроенного просмотра PDF. Нажмите «Скачать оригинал» и откройте страницу " +
                    focusPage +
                    " в PDF-приложении.",
            );
            return;
        }
        try {
            const r = await fetch(
                `/api-proxy/portal/materials/${source.document_id}/original`,
                {
                    headers: { Authorization: `Bearer ${token}` },
                    cache: "no-store",
                },
            );
            if (!r.ok)
                throw new Error(
                    "Оригинал недоступен. Откройте материал заново.",
                );
            setPDF(URL.createObjectURL(await r.blob()));
        } catch (e) {
            setError(e instanceof Error ? e.message : "Не удалось открыть PDF");
        }
    }
    function selectText() {
        const selection = window.getSelection();
        if (!selection?.rangeCount || selection.isCollapsed) return;
        const range = selection.getRangeAt(0);
        const start =
            range.startContainer.parentElement?.closest<HTMLElement>(
                "[data-chunk-id]",
            );
        const end =
            range.endContainer.parentElement?.closest<HTMLElement>(
                "[data-chunk-id]",
            );
        if (!start || start !== end || !text.current?.contains(start)) return;
        const quote = selection.toString().trim().slice(0, 1800);
        if (quote)
            setContext({
                document_id: source.document_id,
                chunk_id: Number(start.dataset.chunkId),
                quote,
            });
    }
    return (
        <section>
            <div className={s.sectionHead}>
                <h2>{source.title}</h2>
                <button autoFocus onClick={onClose}>
                    Закрыть материал
                </button>
            </div>
            <div className={s.actions}>
                {source.source_url?.startsWith("https://") && (
                    <a
                        href={source.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        Открыть страницу в Canvas ↗
                    </a>
                )}
                {source.original_available && (
                    <button onClick={onDownload}>Скачать оригинал</button>
                )}
                {source.original_mime === "application/pdf" && (
                    <button onClick={() => void openPDF()}>
                        Открыть PDF
                        {source.focusPage
                            ? ` · страница ${source.focusPage}`
                            : ""}
                    </button>
                )}
            </div>
            {error && (
                <p role="alert" className={s.error}>
                    {error}
                </p>
            )}
            {pdf && (
                <div>
                    <button onClick={() => setPDF("")}>Закрыть PDF</button>
                    <p className={s.muted}>
                        Страница {focusPage}. Если PDF не отображается,
                        используйте «Скачать оригинал».
                    </p>
                    <iframe
                        className={s.pdfFrame}
                        title="Оригинал PDF"
                        src={`${pdf}#page=${focusPage}`}
                    />
                </div>
            )}
            <div className={s.readerGrid}>
                <div
                    className={s.readingPane}
                    ref={text}
                    onMouseUp={selectText}
                    onTouchEnd={selectText}
                >
                    <p className={s.muted}>
                        {source.published || teacher
                            ? "Выделите текст внутри абзаца или нажмите «Разобрать фрагмент»."
                            : "Проверьте текст и иллюстрации перед публикацией. Разбор в чате станет доступен после публикации."}
                    </p>
                    {!!source.images?.length && (
                        <>
                            <h3>Иллюстрации из материала</h3>
                            <div className={s.illustrations}>
                                {source.images.map((image) => (
                                    <MaterialImage
                                        key={image.id}
                                        image={image}
                                        token={token}
                                    />
                                ))}
                            </div>
                        </>
                    )}
                    {source.chunks.map((c) => (
                        <section
                            key={c.id}
                            className={
                                context.chunk_id === c.id
                                    ? s.highlightChunk
                                    : s.readingChunk
                            }
                        >
                            <div className={s.chunkHeading}>
                                {c.page && <span>Страница {c.page}</span>}
                                <button
                                    disabled={!source.published && !teacher}
                                    onClick={() =>
                                        setContext({
                                            document_id: source.document_id,
                                            chunk_id: c.id,
                                            quote: c.text.slice(0, 1800),
                                        })
                                    }
                                >
                                    Разобрать фрагмент
                                </button>
                            </div>
                            <p data-chunk-id={c.id} className={s.sourceText}>
                                {c.text}
                            </p>
                        </section>
                    ))}
                </div>
                <div className={s.readerChat}>
                    {source.published || teacher ? (
                        <>
                            {context.chunk_id && (
                                <div className={s.actions}>
                                    <button
                                        onClick={() =>
                                            setContext({
                                                document_id: source.document_id,
                                            })
                                        }
                                    >
                                        Весь материал
                                    </button>
                                    {[
                                        [
                                            "Объяснить",
                                            "Объясни выбранный фрагмент простыми словами",
                                        ],
                                        [
                                            "Пример",
                                            "Приведи пример по выбранному фрагменту",
                                        ],
                                    ].map(([label, prompt]) => (
                                        <button
                                            key={label}
                                            onClick={() =>
                                                setSeed({
                                                    text: prompt,
                                                    nonce: Date.now(),
                                                })
                                            }
                                        >
                                            {label}
                                        </button>
                                    ))}
                                </div>
                            )}
                            <CourseChat
                                preview={teacher}
                                key={source.document_id}
                                compact
                                allowReview={allowReview}
                                token={token}
                                api={api}
                                scope={scope}
                                context={context}
                                seed={seed}
                                onSource={onSource}
                            />
                        </>
                    ) : (
                        <p className={s.disclosure}>
                            Это черновик. Чтобы задавать вопросы по нему,
                            сначала опубликуйте материал.
                        </p>
                    )}
                </div>
            </div>
        </section>
    );
}
