import { Head, Html, Main, NextScript } from "next/document";


export default function Document() {
  return (
    <Html lang="ru" data-scroll-behavior="smooth">
      <Head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
