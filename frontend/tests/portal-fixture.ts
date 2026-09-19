import { Route } from "@playwright/test";
export async function fulfillPortal(
    route: Route,
    options: NonNullable<Parameters<Route["fulfill"]>[0]>,
) {
    const path = new URL(route.request().url()).pathname;
    if (
        path.endsWith("/chat/stream") &&
        options.json &&
        (!options.status || options.status < 400)
    ) {
        return route.fulfill({
            contentType: "application/x-ndjson",
            body:
                JSON.stringify({ event: "result", result: options.json }) +
                "\n",
        });
    }
    if (options.json?.chunks)
        options.json = {
            document_id: Number(path.split("/").pop()),
            published: true,
            ...options.json,
        };
    return route.fulfill(options);
}
