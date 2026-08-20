import { Orbit } from "lucide-react";
import { CSSProperties } from "react";
import { COPY, STAR_STREAKS } from "../constants";

type Props = { onEnter: () => void; style: CSSProperties; onPointerMove: (event: React.PointerEvent<HTMLElement>) => void };

export function WorldTransition({ onEnter, onPointerMove, style }: Props) {
  return <main className="world-transition" onPointerMove={onPointerMove} style={style}><div className="world-space-grid" /><div className="world-nebula" /><div className="world-depth-tunnel">{Array.from({ length: 9 }, (_, index) => <i key={index} style={{ "--depth": index } as CSSProperties} />)}</div><div className="warp-stars">{STAR_STREAKS.map((star, index) => <i key={index} style={star} />)}</div><div className="world-fragments">{Array.from({ length: 12 }, (_, index) => <i key={index} style={{ "--fragment": index, "--fragment-size": `${10 + index % 4 * 5}px`, "--fragment-left": `${8 + index * 7}%`, "--fragment-top": `${12 + index % 5 * 16}%` } as CSSProperties} />)}</div><div className="world-portal"><span /><span /><span /><b /><div><Orbit size={34} /><strong>{COPY.traveling}</strong><small>{COPY.leaving}</small></div></div><p>{COPY.aligning}</p><button onClick={onEnter} type="button">{COPY.enter}</button></main>;
}
