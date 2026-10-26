"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Database, Download, FileJson, Package, Scale } from "lucide-react";

import { API_ENDPOINTS } from "@/lib/config";

// The one page in this application that renders for someone with no account.
// It therefore never reads AuthContext and never sends an Authorization
// header: the slug in the URL is the whole credential, and attaching a token
// would only put one into logs that have no use for it.

const FORMAT_LABELS = {
    yolo: { label: "YOLO", hint: "Images, label files and data.yaml", icon: Package },
    coco: { label: "COCO", hint: "A single annotations JSON", icon: FileJson },
};

const num = (value) => (value == null ? "—" : Number(value).toLocaleString());

function Stat({ label, value }) {
    return (
        <div className="border border-white/10 bg-white/[0.02] p-3">
            <p className="text-[10px] uppercase tracking-wider text-gray-500">{label}</p>
            <p className="text-xl font-mono font-semibold mt-1">{value}</p>
        </div>
    );
}

export default function PublicDatasetPage() {
    const { slug } = useParams();
    const [card, setCard] = useState(null);
    const [state, setState] = useState("loading");

    useEffect(() => {
        if (!slug) return;
        let cancelled = false;
        (async () => {
            try {
                const res = await fetch(API_ENDPOINTS.PUBLIC.CARD(slug));
                if (cancelled) return;
                if (res.ok) {
                    setCard(await res.json());
                    setState("ready");
                } else {
                    // The server answers the same way for a slug that never
                    // existed and one that was revoked, and so does this page.
                    setState("missing");
                }
            } catch {
                if (!cancelled) setState("error");
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [slug]);

    if (state === "loading") {
        return (
            <main className="min-h-screen bg-black text-white flex items-center justify-center">
                <p className="text-sm text-gray-500">Loading dataset…</p>
            </main>
        );
    }

    if (state !== "ready") {
        return (
            <main className="min-h-screen bg-black text-white flex items-center justify-center px-6">
                <div className="text-center max-w-md">
                    <Database className="w-8 h-8 text-gray-700 mx-auto mb-3" />
                    <h1 className="text-lg font-semibold">This dataset isn&apos;t available</h1>
                    <p className="text-sm text-gray-500 mt-2">
                        {state === "error"
                            ? "Something went wrong fetching it. Try again in a moment."
                            : "The link may be mistyped, or whoever published it has taken it down."}
                    </p>
                </div>
            </main>
        );
    }

    const { summary } = card;
    const splits = Object.entries(summary.splits || {});

    return (
        <main className="min-h-screen bg-black text-white">
            <div className="max-w-4xl mx-auto px-6 py-12">
                <header className="border-b border-white/10 pb-6">
                    <p className="text-[10px] uppercase tracking-widest text-violet-400">
                        Published dataset
                    </p>
                    <h1 className="text-2xl font-semibold mt-2">{card.title}</h1>
                    {card.description && (
                        <p className="text-sm text-gray-400 mt-3 whitespace-pre-line">
                            {card.description}
                        </p>
                    )}
                    <div className="flex items-center gap-4 mt-4 text-[11px] text-gray-500 flex-wrap">
                        {card.license && (
                            <span className="flex items-center gap-1.5">
                                <Scale className="w-3.5 h-3.5" /> {card.license}
                            </span>
                        )}
                        {card.published_at && (
                            <span>
                                Published {new Date(card.published_at).toLocaleDateString()}
                            </span>
                        )}
                    </div>
                </header>

                <section className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-6">
                    <Stat label="Images" value={num(summary.total_images)} />
                    <Stat label="Boxes" value={num(summary.total_boxes)} />
                    <Stat label="Classes" value={num((summary.classes || []).length)} />
                    <Stat label="Splits" value={num(splits.length)} />
                </section>

                {splits.length > 0 && (
                    <section className="mt-4 flex flex-wrap gap-2">
                        {splits.map(([name, count]) => (
                            <span
                                key={name}
                                className="text-[11px] font-mono border border-white/10 px-2 py-1 text-gray-400"
                            >
                                {name} {num(count)}
                            </span>
                        ))}
                    </section>
                )}

                {(summary.classes || []).length > 0 && (
                    <section className="mt-8">
                        <h2 className="text-sm uppercase tracking-widest text-gray-300">Classes</h2>
                        <div className="mt-3 overflow-x-auto">
                            <table className="w-full text-xs">
                                <thead>
                                    <tr className="text-[10px] uppercase text-gray-500 border-b border-white/10">
                                        <th className="text-left py-2 font-medium">Class</th>
                                        <th className="text-right py-2 font-medium">Boxes</th>
                                    </tr>
                                </thead>
                                <tbody className="font-mono">
                                    {summary.classes.map((entry) => (
                                        <tr key={entry.name} className="border-b border-white/5">
                                            <td className="py-2 font-sans text-gray-200">{entry.name}</td>
                                            <td className="py-2 text-right text-gray-400">
                                                {num(entry.boxes)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </section>
                )}

                {summary.preview_count > 0 && (
                    <section className="mt-8">
                        <h2 className="text-sm uppercase tracking-widest text-gray-300">Samples</h2>
                        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mt-3">
                            {Array.from({ length: summary.preview_count }, (_, index) => (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img
                                    key={index}
                                    src={API_ENDPOINTS.PUBLIC.IMAGE(slug, index)}
                                    alt={`Sample ${index + 1} from ${card.title}`}
                                    loading="lazy"
                                    className="w-full aspect-square object-cover border border-white/10 bg-white/[0.02]"
                                />
                            ))}
                        </div>
                    </section>
                )}

                <section className="mt-8">
                    <h2 className="text-sm uppercase tracking-widest text-gray-300">Download</h2>
                    {!card.downloads_enabled || !card.formats.length ? (
                        <p className="text-xs text-gray-500 mt-3">
                            The publisher has turned downloads off for this dataset.
                        </p>
                    ) : (
                        <div className="flex flex-wrap gap-2 mt-3">
                            {card.formats.map((format) => {
                                const meta = FORMAT_LABELS[format] || {
                                    label: format,
                                    hint: "",
                                    icon: Download,
                                };
                                const Icon = meta.icon;
                                return (
                                    <a
                                        key={format}
                                        href={API_ENDPOINTS.PUBLIC.DOWNLOAD(slug, format)}
                                        className="flex items-center gap-2 border border-violet-500/40 bg-violet-500/10 px-3 py-2 text-xs text-violet-200 hover:bg-violet-500/20 transition-colors"
                                    >
                                        <Icon className="w-3.5 h-3.5" />
                                        <span>
                                            {meta.label}
                                            {meta.hint && (
                                                <span className="text-gray-500 ml-2 hidden sm:inline">
                                                    {meta.hint}
                                                </span>
                                            )}
                                        </span>
                                    </a>
                                );
                            })}
                        </div>
                    )}
                </section>

                <footer className="mt-12 pt-6 border-t border-white/10 text-[11px] text-gray-600">
                    Published from a frozen dataset version, so this link keeps describing
                    the same data. Built with NebulaML.
                </footer>
            </div>
        </main>
    );
}
