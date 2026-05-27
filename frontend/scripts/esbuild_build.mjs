import { cpSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as esbuild from "esbuild";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
const assets = join(dist, "assets");

mkdirSync(assets, { recursive: true });

const result = await esbuild.build({
  absWorkingDir: root,
  entryPoints: ["src/main.jsx"],
  bundle: true,
  outfile: join(assets, "index.js"),
  format: "esm",
  platform: "browser",
  target: "es2020",
  loader: { ".jsx": "jsx", ".css": "css" },
  jsx: "automatic",
  minify: true,
  sourcemap: true,
  define: { "process.env.NODE_ENV": '"production"' },
  metafile: true,
  logLevel: "info",
});

const cssFiles = Object.keys(result.metafile.outputs).filter((p) => p.endsWith(".css"));
let cssName = "index.css";
if (cssFiles.length === 1) {
  const built = cssFiles[0];
  cssName = built.split(/[/\\]/).pop() || cssName;
} else if (cssFiles.length > 1) {
  throw new Error(`unexpected css outputs: ${cssFiles.join(", ")}`);
}

const html = readFileSync(join(root, "index.html"), "utf8")
  .replace(/\/src\/main\.jsx/, `/assets/index.js`)
  .replace(
    /<link rel="stylesheet"[^>]*href="[^"]*"[^>]*>\s*/i,
    `<link rel="stylesheet" crossorigin href="/assets/${cssName}">\n`
  );
writeFileSync(join(dist, "index.html"), html, "utf8");

try {
  cpSync(join(root, "public"), dist, { recursive: true, force: true });
} catch {
  // optional
}

writeFileSync(join(root, "build-esbuild.ok"), "ok\n", "utf8");
console.log("esbuild build OK", join(dist, "index.html"));
