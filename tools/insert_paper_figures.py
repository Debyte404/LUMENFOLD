"""insert_figures.py -- wire the figure environments into the paper sections.

Anchors are unique \\subsection headings, inserted BEFORE, because the
\\bottomrule/\\end{tabular} tail is not unique across a file with several tables.
"""
import io

P = "D:/ValueProjects/caustics/docs/paper/sections"


def before(path, anchor, block):
    s = io.open(path, encoding="utf-8").read()
    n = s.count(anchor)
    assert n == 1, f"{path}: anchor appears {n} times: {anchor[:50]}"
    s = s.replace(anchor, block.strip() + "\n\n" + anchor)
    io.open(path, "w", encoding="utf-8", newline="").write(s)
    print(f"  ok {path.split('/')[-1]:<18} {block.strip().splitlines()[1][:44]}")


FIG1 = r"""
\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{figures/fig1_scene.pdf}
\caption{The test scene drawn to scale. The glass body, water column, wall
thickness, fill height and receiver are shown at true relative size with
dimension lines; the ray path is traced through the actual geometry of
Section~\ref{sec:scene} at the central channel index rather than sketched. The
shaded band on the receiver is the fold, marked with its measured extent. All
lengths in millimetres.}
\label{fig:scene}
\end{figure*}
"""

FIG2 = r"""
\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{figures/fig2_fold.pdf}
\caption{The ray map of \eqref{eq:raymap}, computed by the independent
brute-force trace of Section~\ref{sec:results-quality} rather than by the
solver. The density in (a) is the caustic; the bright ridge is where
$|\detJ| \to 0$. Panel (b) cuts through it in raw ray counts. The sharpness of
that peak is what Lemma~\ref{lem:diverge} says no quadrature can bound.}
\label{fig:fold}
\end{figure*}
"""

FIG3 = r"""
\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{figures/fig3_airy.pdf}
\caption{Panel (a): the fold intensity $|\Ai(-u)|^2$ used by the correction
\eqref{eq:profile}, computed with \texttt{scipy.special.airy}. It is bounded,
peaks at $X = 1.0188$ \emph{beside} the fold rather than on it, and its
oscillations tighten toward the fold. Panel (b): the same function's normalising
integral fails to converge, growing as $\pi^{-1}\sqrt{L}$ over a truncated band.
That is Lemma~\ref{lem:notl1}, and it is why the correction is a discrete band
ratio \eqref{eq:kstar} rather than a constant.}
\label{fig:airy}
\end{figure*}
"""

FIG4 = r"""
\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{figures/fig4_field.pdf}
\caption{Our baked field. Panel (a) is normalised to its own maximum and shown
at $\gamma = 2.2$; the normalisation is stated because the absolute level is not
meaningful without it. Panel (b) is a horizontal cut per channel at the linear
level. The channels separate because \eqref{eq:sellmeier} and
\eqref{eq:perchannel} give them different indices and widths, not because any
effect was added on top.}
\label{fig:field}
\end{figure*}
"""

FIG5 = r"""
\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{figures/fig5_quality.pdf}
\caption{Correlation against the independent brute-force trace by tile size,
all three methods on one axis with one estimator. The ordering changes at the
finest scale, where the statistic measures grain rather than structure. Log
axis on tile size.}
\label{fig:quality}
\end{figure}
"""

FIG6 = r"""
\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{figures/fig6_fourpanel.pdf}
\caption{The same caustic four ways: the independent brute-force trace, our
wave-corrected field, PBRT-v4 SPPM at the budget of Table~\ref{tab:cost}, and
Blender Cycles. Each panel is normalised to its own maximum at $\gamma = 0.45$,
so the comparison is of structure than of absolute level. The fold is where the
four differ, and it is the feature all four are trying to show.}
\label{fig:fourpanel}
\end{figure*}
"""

FIG7 = r"""
\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{figures/fig7_cost.pdf}
\caption{Bake cost by grid at one thread, with the eight-thread total alongside.
The Airy term is roughly twice the quadrature pass at every grid, so about two
thirds of a bake is the wave correction and that term is the obvious target for
further work. Log scale on time.}
\label{fig:cost}
\end{figure}
"""

FIG8 = r"""
\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{figures/fig8_dispersion.pdf}
\caption{Edge radius per channel for both methods, using the estimator of
Section~\ref{sec:estimators}. Both order $R > G > B$ and both show the same
$+\SI{5.0}{\milli\meter}$ red--blue split, which is what the measured indices
predict. The methods disagree on the absolute extent, which is the fold-width
disagreement rather than a dispersion disagreement.}
\label{fig:dispersion}
\end{figure}
"""

FIG9 = r"""
\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{figures/fig9_efficiency.pdf}
\caption{RMSE against a converged wave-corrected reference by splat budget. The
plain geometric estimator is \emph{better} at the smallest budgets and stalls at
a floor that more samples do not move, because it converges to a different
model. The regime where our method loses is drawn rather than omitted.}
\label{fig:efficiency}
\end{figure}
"""

FIG10 = r"""
\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{figures/fig10_ripple.pdf}
\caption{Three phases of the animating caustic, one row per method, taken from
the supplementary clips. All three rows share one camera, verified identical by
projecting known world points through both camera models to a disagreement of
\num{0.0000}, and all three use the \emph{physical} fringe width rather than a
visibility-exaggerated one, so the colour shown is the measured dispersion. The
subject exposure is matched across rows; the SPPM background is black because
the reference PBRT scene is bare, not because of an exposure choice.}
\label{fig:ripple}
\end{figure*}
"""

before(f"{P}/kinematics.tex", r"\subsection{The surface and its normal}", FIG1)
before(f"{P}/kinematics.tex", r"\subsection{The normal form of the fold, and the Airy profile}", FIG2)
before(f"{P}/kinematics.tex", r"\subsection{The profile as implemented}", FIG3)

before(f"{P}/results.tex", r"\subsection{Quality against the reference conforming solver}", FIG4)
before(f"{P}/results.tex", r"\subsection{Cost against quality, including where we lose}", FIG5)
before(f"{P}/results.tex", r"\subsection{Tail behaviour}", FIG6)
before(f"{P}/results.tex", r"\subsection{Dispersion}", FIG7)
before(f"{P}/results.tex", r"\subsection{Temporal behaviour}", FIG8)
before(f"{P}/results.tex", r"\subsection{Ablations}", FIG9)
before(f"{P}/results.tex", r"\subsection{Resolution and phase studies}", FIG10)

print("done")
