import type { AppProps } from "next/app";

import "../styles/globals.css";
import "../styles/workshop-production.css";

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className="workshop-product" data-design-system="workshop-route">
      <Component {...pageProps} />
    </div>
  );
}
