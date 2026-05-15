(function () {
  const container = document.getElementById("harbor-maplibre-map");
  if (!container || !window.maplibregl) {
    return;
  }

  let vessels = [];
  let bounds = null;
  try {
    vessels = JSON.parse(container.dataset.vessels || "[]");
    bounds = JSON.parse(container.dataset.bounds || "null");
  } catch (error) {
    container.textContent = "Map data unavailable.";
    return;
  }

  const southwest = bounds && bounds.sw ? bounds.sw : [42.28, -71.08];
  const northeast = bounds && bounds.ne ? bounds.ne : [42.38, -70.92];
  const center = [
    (Number(southwest[1]) + Number(northeast[1])) / 2,
    (Number(southwest[0]) + Number(northeast[0])) / 2,
  ];

  const map = new maplibregl.Map({
    container,
    center,
    zoom: 11.4,
    pitch: 0,
    bearing: 0,
    attributionControl: true,
    style: {
      version: 8,
      sources: {
        "carto-dark": {
          type: "raster",
          tiles: ["https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png", "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png", "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: "Map tiles by CARTO, data by OpenStreetMap",
        },
        seamarks: {
          type: "raster",
          tiles: ["https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: "Sea marks by OpenSeaMap contributors",
        },
      },
      layers: [
        { id: "carto-dark", type: "raster", source: "carto-dark" },
        { id: "seamarks", type: "raster", source: "seamarks" },
      ],
    },
  });

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
  map.fitBounds(
    [
      [Number(southwest[1]), Number(southwest[0])],
      [Number(northeast[1]), Number(northeast[0])],
    ],
    { padding: 32, maxZoom: 12.8, duration: 0 }
  );

  const typeClass = (type) => `marker-${String(type || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "unknown"}`;
  const detail = (label, value) => value || value === 0 ? `<p><span>${label}</span><strong>${value}</strong></p>` : "";

  vessels
    .filter((vessel) => vessel.lat && vessel.lon)
    .forEach((vessel) => {
      const element = document.createElement("button");
      element.type = "button";
      element.className = `maplibre-vessel-marker ${typeClass(vessel.type)}`;
      element.setAttribute("aria-label", `${vessel.name || "Unknown vessel"} vessel marker`);
      element.setAttribute("data-vessel-type", vessel.type || "unknown");
      element.setAttribute("data-mmsi", vessel.mmsi || "");

      const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: true, offset: 16 }).setHTML(`
        <article class="map-popup">
          <h2>${vessel.name || "Unknown vessel"}</h2>
          ${detail("MMSI", vessel.mmsi)}
          ${detail("Type", vessel.type)}
          ${detail("Speed", vessel.speed_knots || vessel.speed_knots === 0 ? `${vessel.speed_knots} kt` : "")}
          ${detail("Heading", vessel.heading || vessel.heading === 0 ? `${vessel.heading} deg` : "")}
          ${detail("Destination", vessel.destination)}
          ${detail("ETA", vessel.eta)}
          ${detail("Last signal", vessel.last_signal)}
        </article>
      `);

      new maplibregl.Marker({ element, anchor: "center" })
        .setLngLat([Number(vessel.lon), Number(vessel.lat)])
        .setPopup(popup)
        .addTo(map);
    });

  map.on("load", () => {
    container.closest(".harbor-map")?.classList.add("maplibre-loaded");
  });
})();
