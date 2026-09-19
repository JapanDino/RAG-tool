import { useEffect, useState } from "react";
import s from "../styles/portal.module.css";

export type Illustration = {
    id: number;
    document_id: number;
    caption: string;
    location: string;
    page?: number;
    width: number;
    height: number;
};

export default function MaterialImage({ image, token, onSource, disabled }: {
    image: Illustration;
    token: string;
    onSource?: () => void;
    disabled?: boolean;
}) {
    const [url, setUrl] = useState("");
    const [failed, setFailed] = useState(false);
    useEffect(() => {
        const controller = new AbortController();
        let objectUrl = "";
        setUrl("");
        setFailed(false);
        fetch(`/api-proxy/portal/materials/${image.document_id}/images/${image.id}`, {
            headers: { Authorization: `Bearer ${token}` },
            cache: "no-store",
            signal: controller.signal,
        }).then(async (response) => {
            if (!response.ok) throw new Error("Image unavailable");
            const blob = await response.blob();
            if (controller.signal.aborted) return;
            objectUrl = URL.createObjectURL(blob);
            setUrl(objectUrl);
        }).catch(() => {
            if (!controller.signal.aborted) setFailed(true);
        });
        return () => {
            controller.abort();
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [image.document_id, image.id, token]);

    return <figure className={s.illustration}>
        {url ? (
            // Protected images use an authenticated fetch and a short-lived local blob URL.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={image.caption} width={image.width} height={image.height}
                onError={() => { setUrl(""); setFailed(true); }} />
        ) : <p role="status">{failed ? "Иллюстрация недоступна. Материал мог быть скрыт." : "Загружаем иллюстрацию…"}</p>}
        <figcaption>
            <span>{image.caption}</span>
            <span className={s.muted}>{image.location} · Из исходного материала</span>
            {onSource && <button type="button" disabled={disabled} onClick={onSource}>Открыть источник иллюстрации</button>}
        </figcaption>
    </figure>;
}
