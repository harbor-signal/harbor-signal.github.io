(function () {
  const container = document.getElementById("harbor-leaflet-map");
  if (!container || !window.L) {
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

  const map = L.map(container, {
    scrollWheelZoom: false,
    zoomControl: true,
  });

  const southwest = bounds && bounds.sw ? bounds.sw : [42.28, -71.08];
  const northeast = bounds && bounds.ne ? bounds.ne : [42.38, -70.92];
  map.fitBounds([southwest, northeast], { padding: [18, 18] });

  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    maxZoom: 19,
  }).addTo(map);

  L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", {
    attribution: "Sea marks &copy; OpenSeaMap contributors",
    maxZoom: 18,
  }).addTo(map);

  const typeClass = (type) => `marker-${String(type || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "unknown"}`;
  const popupLine = (label, value) => value ? `<p><span>${label}</span><strong>${value}</strong></p>` : "";

  vessels
    .filter((vessel) => vessel.lat && vessel.lon)
    .forEach((vessel) => {
      const marker = L.marker([Number(vessel.lat), Number(vessel.lon)], {
        title: `${vessel.name} / ${vessel.type}`,
        icon: L.divIcon({
          className: `leaflet-vessel-marker ${typeClass(vessel.type)}`,
          html: "<span></span>",
          iconSize: [18, 18],
          iconAnchor: [9, 9],
        }),
      }).addTo(map);

      marker.bindPopup(`
        <article class="map-popup">
          <h2>${vessel.name || "Unknown vessel"}</h2>
          ${popupLine("Type", vessel.type)}
          ${popupLine("MMSI", vessel.mmsi)}
          ${popupLine("Speed", vessel.speed_knots ? `${vessel.speed_knots} kt` : "")}
          ${popupLine("Heading", vessel.heading ? `${vessel.heading} deg` : "")}
          ${popupLine("Destination", vessel.destination)}
          ${popupLine("Source", vessel.source)}
        </article>
      `);

      const element = marker.getElement();
      if (element) {
        element.setAttribute("data-vessel-type", vessel.type || "unknown");
        element.setAttribute("data-mmsi", vessel.mmsi || "");
      }
    });

  container.closest(".harbor-map")?.classList.add("leaflet-loaded");
})();
