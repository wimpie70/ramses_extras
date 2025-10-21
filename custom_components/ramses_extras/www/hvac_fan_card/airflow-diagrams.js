export const AIRFLOW_DIAGRAMS_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800">
<defs>
<symbol id="gradientsAndMarkers">
<linearGradient id="blueToRed" x1="212" y1="212" x2="588" y2="588" gradientUnits="userSpaceOnUse">
<stop offset="0%" stop-color="blue"/>
<stop offset="100%" stop-color="red"/>
</linearGradient>
<linearGradient id="redToBlue" x1="212" y1="212" x2="588" y2="588" gradientUnits="userSpaceOnUse">
<stop offset="0%" stop-color="red"/>
<stop offset="100%" stop-color="blue"/>
</linearGradient>
<linearGradient id="silverToGray" x1="620" y1="340" x2="180" y2="340" gradientUnits="userSpaceOnUse">
<stop offset="0%" stop-color="silver"/>
<stop offset="100%" stop-color="gray"/>
</linearGradient>
<marker markerWidth="5" markerHeight="5" refX="2.5" refY="2.5" viewBox="0 0 5 5" orient="auto" id="marker1">
<polygon points="0,5 1.6667,2.5 0,0 5,2.5" fill="red"/>
</marker>
<marker markerWidth="5" markerHeight="5" refX="2.5" refY="2.5" viewBox="0 0 5 5" orient="auto" id="marker2">
<polygon points="0,5 1.6667,2.5 0,0 5,2.5" fill="blue"/>
</marker>
</symbol>
<symbol id="outerHexagon">
<g stroke="grey" stroke-width="1" fill="url(#silverToGray)">
<polygon points="
297,132
503,132
620,340
503,548
297,548
180,340
"></polygon>
</g>
</symbol>
<symbol id="innerHexagon">
<g stroke="silver" stroke-width="1" fill="silver">
<polygon points="
337,176
483,176
573,330
483,484
337,484
247,330
"></polygon>
</g>
</symbol>
<symbol id="sidesHexagon">
<g>
<line x1="337" y1="176" x2="297" y2="132" stroke="silver" stroke-width="4"></line>
<line x1="483" y1="176" x2="503" y2="132" stroke="silver" stroke-width="4"></line>
<line x1="573" y1="330" x2="620" y2="340" stroke="silver" stroke-width="4"></line>
<line x1="483" y1="484" x2="503" y2="548" stroke="silver" stroke-width="4"></line>
<line x1="337" y1="484" x2="297" y2="548" stroke="silver" stroke-width="4"></line>
<line x1="247" y1="330" x2="180" y2="340" stroke="silver" stroke-width="4"></line>
</g>
</symbol>
<symbol id="heatRecoveryArrows">
<g stroke-width="29" stroke="url(#blueToRed)" fill="none" stroke-linecap="round" stroke-linejoin="round"
  transform="translate(0,-70) translate(400,400) scale(1.3) translate(-400,-400)">
  <path d="M212 212 Q374 307 400 400 Q455 569 588 588" marker-end="url(#marker1)"></path>
</g>
<g stroke-width="29" stroke="white" fill="none" stroke-linecap="round" stroke-linejoin="round"
  transform="translate(0,-70) scale(-1,1) translate(-800,0) translate(400,400) scale(1.35) translate(-400,-400)">
  <path d="M212 212 Q374 307 400 400 Q455 569 588 588"></path>
</g>
<g stroke-width="29" stroke="url(#redToBlue)" fill="none" stroke-linecap="round" stroke-linejoin="round"
  transform="translate(0,-70) scale(-1,1) translate(-800,0) translate(400,400) scale(1.3) translate(-400,-400)">
  <path d="M212 212 Q374 307 400 400 Q455 569 588 588" marker-end="url(#marker2)"></path>
</g>
</symbol>
<symbol id="bypassArrows">
<g stroke-width="29" stroke="url(#blueToRed)" fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path d="M180 340 L620 340" marker-end="url(#marker1)"></path>
  <path d="M620 340 L180 340" marker-end="url(#marker2)"></path>
</g>
</symbol>
<symbol id="outerOutline">
<g stroke="grey" stroke-width="20" fill="none">
  <polygon points="
    297,132
    503,132
    620,340
    503,548
    297,548
    180,340
  "></polygon>
</g>
</symbol>
</defs>
<g id="normalMode">
  <use href="#gradientsAndMarkers" />
  <use href="#outerHexagon" />
  <use href="#innerHexagon" />
  <use href="#sidesHexagon" />
  <use href="#heatRecoveryArrows" />
  <use href="#outerOutline" />
</g>
<g id="bypassOpenMode">
  <use href="#gradientsAndMarkers" />
  <use href="#outerHexagon" />
  <use href="#innerHexagon" />
  <use href="#sidesHexagon" />
  <use href="#bypassArrows" />
  <use href="#outerOutline" />
</g>
</svg>`;

export const NORMAL_SVG = `
  <svg viewBox="0 0 800 800" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="blueToRed" x1="212" y1="212" x2="588" y2="588" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="blue"/>
        <stop offset="100%" stop-color="red"/>
      </linearGradient>

      <linearGradient id="redToBlue" x1="212" y1="212" x2="588" y2="588" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="red"/>
        <stop offset="100%" stop-color="blue"/>
      </linearGradient>

      <linearGradient id="silverToGray" x1="620" y1="340" x2="180" y2="340" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="silver"/>
        <stop offset="100%" stop-color="gray"/>
      </linearGradient>

      <marker markerWidth="5" markerHeight="5" refX="2.5" refY="2.5" viewBox="0 0 5 5" orient="auto" id="marker1">
        <polygon points="0,5 1.6667,2.5 0,0 5,2.5" fill="red"></polygon>
      </marker>

      <marker markerWidth="5" markerHeight="5" refX="2.5" refY="2.5" viewBox="0 0 5 5" orient="auto" id="marker2">
        <polygon points="0,5 1.6667,2.5 0,0 5,2.5" fill="blue"></polygon>
      </marker>
    </defs>

    <!-- Outer hexagon sides (scaled 1.35× around center 400,340) -->
    <g stroke="grey" stroke-width="1" fill="url(#silverToGray)">
      <polygon points="
        297,132
        503,132
        620,340
        503,548
        297,548
        180,340
      "></polygon>
    </g>

    <!-- Inner hexagon -->
    <g stroke="silver" stroke-width="1" fill="silver">
      <polygon points="
        337,176
        483,176
        573,330
        483,484
        337,484
        247,330
      "></polygon>
    </g>
    <!-- Connection lines hexagons -->
    <g>
      <line x1="337" y1="176" x2="297" y2="132" stroke="silver" stroke-width="4"></line>
      <line x1="483" y1="176" x2="503" y2="132" stroke="silver" stroke-width="4"></line>
      <line x1="573" y1="330" x2="620" y2="340" stroke="silver" stroke-width="4"></line>
      <line x1="483" y1="484" x2="503" y2="548" stroke="silver" stroke-width="4"></line>
      <line x1="337" y1="484" x2="297" y2="548" stroke="silver" stroke-width="4"></line>
      <line x1="247" y1="330" x2="180" y2="340" stroke="silver" stroke-width="4"></line>
    </g>

    <!-- Original arrows for heat recovery -->
    <g stroke-width="29" stroke="url(#blueToRed)" fill="none" stroke-linecap="round" stroke-linejoin="round"
      transform="translate(0,-70) translate(400,400) scale(1.3) translate(-400,-400)">
      <path d="M212 212 Q374 307 400 400 Q455 569 588 588" marker-end="url(#marker1)"></path>
    </g>

    <!-- Mirrored arrow shadow -->
    <g stroke-width="29" stroke="white" fill="none" stroke-linecap="round" stroke-linejoin="round"
      transform="translate(0,-70) scale(-1,1) translate(-800,0) translate(400,400) scale(1.35) translate(-400,-400)">
      <path d="M212 212 Q374 307 400 400 Q455 569 588 588"></path>
    </g>

    <!-- Mirrored arrow -->
    <g stroke-width="29" stroke="url(#redToBlue)" fill="none" stroke-linecap="round" stroke-linejoin="round"
      transform="translate(0,-70) scale(-1,1) translate(-800,0) translate(400,400) scale(1.3) translate(-400,-400)">
      <path d="M212 212 Q374 307 400 400 Q455 569 588 588" marker-end="url(#marker2)"></path>
    </g>

    <!-- Outer hexagon outline -->
    <g stroke="grey" stroke-width="20" fill="none">
      <polygon points="
        297,132
        503,132
        620,340
        503,548
        297,548
        180,340
      "></polygon>
    </g>
  </svg>
`;

export const BYPASS_OPEN_SVG = `
  <svg viewBox="0 0 800 800" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="blueToRed" x1="212" y1="212" x2="588" y2="588" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="blue"/>
        <stop offset="100%" stop-color="red"/>
      </linearGradient>

      <linearGradient id="redToBlue" x1="212" y1="212" x2="588" y2="588" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="red"/>
        <stop offset="100%" stop-color="blue"/>
      </linearGradient>

      <linearGradient id="silverToGray" x1="620" y1="340" x2="180" y2="340" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="silver"/>
        <stop offset="100%" stop-color="gray"/>
      </linearGradient>

      <marker markerWidth="5" markerHeight="5" refX="2.5" refY="2.5" viewBox="0 0 5 5" orient="auto" id="marker1">
        <polygon points="0,5 1.6667,2.5 0,0 5,2.5" fill="red"></polygon>
      </marker>

      <marker markerWidth="5" markerHeight="5" refX="2.5" refY="2.5" viewBox="0 0 5 5" orient="auto" id="marker2">
        <polygon points="0,5 1.6667,2.5 0,0 5,2.5" fill="blue"></polygon>
      </marker>
    </defs>

    <!-- Outer hexagon sides (scaled 1.35× around center 400,340) -->
    <g stroke="grey" stroke-width="1" fill="url(#silverToGray)">
      <polygon points="
        297,132
        503,132
        620,340
        503,548
        297,548
        180,340
      "></polygon>
    </g>

    <!-- Inner hexagon -->
    <g stroke="silver" stroke-width="1" fill="silver">
      <polygon points="
        337,176
        483,176
        573,330
        483,484
        337,484
        247,330
      "></polygon>
    </g>
    <!-- Connection lines hexagons -->
    <g>
      <line x1="337" y1="176" x2="297" y2="132" stroke="silver" stroke-width="4"></line>
      <line x1="483" y1="176" x2="503" y2="132" stroke="silver" stroke-width="4"></line>
      <line x1="573" y1="330" x2="620" y2="340" stroke="silver" stroke-width="4"></line>
      <line x1="483" y1="484" x2="503" y2="548" stroke="silver" stroke-width="4"></line>
      <line x1="337" y1="484" x2="297" y2="548" stroke="silver" stroke-width="4"></line>
      <line x1="247" y1="330" x2="180" y2="340" stroke="silver" stroke-width="4"></line>
    </g>

    <!-- Horizontal arrows for bypass open (fresh air bypasses heat exchanger) -->
    <g stroke-width="29" stroke="url(#blueToRed)" fill="none" stroke-linecap="round" stroke-linejoin="round">
      <!-- Horizontal arrow from left to right (fresh air in) -->
      <path d="M180 340 L620 340" marker-end="url(#marker1)"></path>
      <!-- Horizontal arrow from right to left (exhaust air out) -->
      <path d="M620 340 L180 340" marker-end="url(#marker2)"></path>
    </g>

    <!-- Outer hexagon outline -->
    <g stroke="grey" stroke-width="20" fill="none">
      <polygon points="
        297,132
        503,132
        620,340
        503,548
        297,548
        180,340
      "></polygon>
    </g>
  </svg>
`;
