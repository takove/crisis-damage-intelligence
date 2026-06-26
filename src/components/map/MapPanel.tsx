"use client";

import { useCallback, useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { AoiRecord, DamageFeature, VlmRecord } from "../types";

declare global {
  interface Window {
    __damageMapDebug?: {
      visibleFeatures: string[];
      selectedId?: string;
      center?: { lat: number; lng: number };
      zoom?: number;
      filter: Props["filter"];
      mode: Props["mode"];
    };
  }
}

type Props = {
  aoi: AoiRecord;
  mode: "before" | "after";
  opacity: number;
  filter: "all" | "severe" | "vlm";
  vlm: Record<string, VlmRecord>;
  selectedId?: string;
  onSelect: (feature: DamageFeature) => void;
};

function damageClass(properties: DamageFeature["properties"], vlm?: VlmRecord) {
  const vlmClass = vlm?.vlm?.damage_class;
  const raw = String(vlmClass ?? properties.damage_class ?? properties.damage_gra ?? properties.confirmed_damage_class ?? "").toLowerCase();
  if (raw.includes("possibly")) return "possible";
  if (raw.includes("destroy") || raw.includes("major") || raw === "damaged" || raw === "major_damage") return "severe";
  if (raw.includes("minor") || raw.includes("possible")) return "possible";
  if (raw.includes("uncertain")) return "uncertain";
  return "low";
}

function colorFor(kind: string) {
  if (kind === "severe") return "#c42128";
  if (kind === "possible") return "#d78a1f";
  if (kind === "uncertain") return "#64748b";
  return "#7a7f87";
}

function passesFilter(feature: DamageFeature, filter: Props["filter"], vlm: Record<string, VlmRecord>) {
  const id = feature.properties.id;
  if (filter === "vlm") return Boolean(vlm[id]);
  if (filter === "severe") return damageClass(feature.properties, vlm[id]) === "severe";
  return true;
}

export default function MapPanel({ aoi, mode, opacity, filter, vlm, selectedId, onSelect }: Props) {
  const nodeRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const beforeRef = useRef<L.ImageOverlay | null>(null);
  const afterRef = useRef<L.ImageOverlay | null>(null);
  const vectorRef = useRef<L.GeoJSON | null>(null);
  const selectedMarkerRef = useRef<L.Marker | null>(null);
  const afterPaneRef = useRef<HTMLElement | null>(null);
  const featuresRef = useRef<DamageFeature[]>([]);
  const layerByIdRef = useRef<Map<string, L.Layer>>(new Map());
  const highlightRef = useRef<L.GeoJSON | null>(null);
  const visibleCountRef = useRef(0);
  const modeRef = useRef(mode);
  const selectedIdRef = useRef(selectedId);

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const renderVectors = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    vectorRef.current?.remove();
    layerByIdRef.current.clear();
    const features = featuresRef.current.filter((feature) => passesFilter(feature, filter, vlm));
    visibleCountRef.current = features.length;
    nodeRef.current?.setAttribute("data-visible-features", String(features.length));
    window.__damageMapDebug = {
      ...(window.__damageMapDebug ?? {}),
      visibleFeatures: features.map((feature) => feature.properties.id),
      selectedId: selectedIdRef.current,
      center: map.getCenter(),
      zoom: map.getZoom(),
      filter,
      mode: modeRef.current,
    };
    vectorRef.current = L.geoJSON({ type: "FeatureCollection", features } as GeoJSON.FeatureCollection, {
      pane: "damage-vectors",
      interactive: true,
      style: (feature) => {
        const typed = feature as DamageFeature;
        const kind = damageClass(typed.properties, vlm[typed.properties.id]);
        const c = colorFor(kind);
        return { color: c, fillColor: c, fillOpacity: opacity, opacity, weight: kind === "low" ? 1 : 2 };
      },
      onEachFeature: (feature, layer) => {
        const typed = feature as DamageFeature;
        layerByIdRef.current.set(typed.properties.id, layer);
        layer.on("click", () => onSelect(typed));
        const p = typed.properties;
        layer.bindTooltip(`${p.id}<br>${p.damage_class ?? p.damage_gra ?? ""}`, { sticky: true });
        layer.bindPopup(popupHtml(p));
      },
    }).addTo(map);
  }, [filter, onSelect, opacity, vlm]);

  useEffect(() => {
    if (!nodeRef.current || mapRef.current) return;
    const map = L.map(nodeRef.current, { zoomControl: false, preferCanvas: true });
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 20,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    map.createPane("raster-before").style.zIndex = "350";
    afterPaneRef.current = map.createPane("raster-after");
    afterPaneRef.current.style.zIndex = "360";
    map.createPane("damage-vectors").style.zIndex = "520";
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    beforeRef.current?.remove();
    afterRef.current?.remove();
    beforeRef.current = null;
    afterRef.current = null;
    featuresRef.current = [];
    vectorRef.current?.remove();
    vectorRef.current = null;

    const bounds = L.latLngBounds(aoi.bounds);
    if (aoi.layers.beforeImage) {
      beforeRef.current = L.imageOverlay(aoi.layers.beforeImage, bounds, { pane: "raster-before", opacity: 1 }).addTo(map);
    }
    if (aoi.layers.afterImage) {
      afterRef.current = L.imageOverlay(aoi.layers.afterImage, bounds, { pane: "raster-after", opacity: 1 }).addTo(map);
      afterRef.current.once("load", () => applyRasterMode(modeRef.current, beforeRef.current, afterRef.current, afterPaneRef.current));
    }
    fetch(aoi.layers.damage)
      .then((r) => r.json())
      .then((data: GeoJSON.FeatureCollection) => {
        featuresRef.current = data.features as DamageFeature[];
        renderVectors();
      });
    map.fitBounds(bounds.pad(0.12));
  }, [aoi, renderVectors]);

  useEffect(() => {
    renderVectors();
  }, [renderVectors]);

  useEffect(() => {
    applyRasterMode(mode, beforeRef.current, afterRef.current, afterPaneRef.current);
  }, [mode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId) return;
    const feature = featuresRef.current.find((candidate) => candidate.properties.id === selectedId);
    if (!feature) return;
    const layer = layerByIdRef.current.get(selectedId);
    const bounds = layer && "getBounds" in layer ? (layer as L.Polygon).getBounds() : L.geoJSON(feature as GeoJSON.Feature).getBounds();
    if (!bounds.isValid()) return;
    highlightRef.current?.remove();
    selectedMarkerRef.current?.remove();
    highlightRef.current = L.geoJSON(feature as GeoJSON.Feature, {
      pane: "damage-vectors",
      interactive: false,
      style: {
        color: "#ffffff",
        fillColor: "#ffffff",
        fillOpacity: 0.08,
        opacity: 1,
        weight: 5,
      },
    }).addTo(map);
    const center = bounds.getCenter();
    map.setView(center, 18, { animate: false });
    selectedMarkerRef.current = L.marker(center, {
      pane: "markerPane",
      interactive: true,
      icon: L.divIcon({
        className: "selected-building-marker",
        html: "<span></span>",
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      }),
    }).addTo(map);
    selectedMarkerRef.current.bindPopup(popupHtml(feature.properties)).openPopup();
    nodeRef.current?.setAttribute("data-focused-id", selectedId);
    nodeRef.current?.setAttribute("data-map-center", `${center.lat.toFixed(7)},${center.lng.toFixed(7)}`);
    window.__damageMapDebug = {
      ...(window.__damageMapDebug ?? {}),
      visibleFeatures: window.__damageMapDebug?.visibleFeatures ?? [],
      selectedId,
      center,
      zoom: map.getZoom(),
      filter,
      mode: modeRef.current,
    };
    window.setTimeout(() => {
      highlightRef.current?.bringToFront();
      nodeRef.current?.setAttribute("data-map-zoom", String(map.getZoom()));
      window.__damageMapDebug = {
        ...(window.__damageMapDebug ?? {}),
        visibleFeatures: window.__damageMapDebug?.visibleFeatures ?? [],
        filter,
        mode: modeRef.current,
        center: map.getCenter(),
        zoom: map.getZoom(),
      };
    }, 50);
  }, [selectedId, filter]);

  return <div ref={nodeRef} className="map-node" data-filter={filter} data-mode={mode} data-opacity={opacity} data-selected-id={selectedId ?? ""} />;
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function popupHtml(p: DamageFeature["properties"]) {
  const mapsUrl = typeof p.google_maps_url === "string" ? p.google_maps_url : "";
  return (
    `<strong>${escapeHtml(p.id)}</strong><br/>` +
    `EMS: <strong>${escapeHtml(String(p.damage_gra ?? p.damage_class ?? "unknown"))}</strong><br/>` +
    `Score: ${escapeHtml(String(p.damage_score ?? p.damage_percent ?? "-"))}<br/>` +
    (mapsUrl ? `<a href="${escapeHtml(mapsUrl)}" target="_blank" rel="noreferrer">Google Maps</a>` : "")
  );
}

function applyRasterMode(
  mode: Props["mode"],
  beforeLayer: L.ImageOverlay | null,
  afterLayer: L.ImageOverlay | null,
  afterPane: HTMLElement | null,
) {
  if (!beforeLayer || !afterLayer || !afterPane) return;
  const beforeEl = beforeLayer.getElement();
  const afterEl = afterLayer.getElement();
  if (!beforeEl || !afterEl) return;
  const isBefore = mode === "before";
  const isAfter = mode === "after";
  beforeLayer.setOpacity(isAfter ? 0 : 1);
  afterLayer.setOpacity(isBefore ? 0 : 1);
  afterPane.style.clipPath = "none";
  afterPane.style.setProperty("-webkit-clip-path", "none");
  afterPane.style.overflow = "hidden";
  afterEl.style.clipPath = "none";
  afterEl.style.setProperty("-webkit-clip-path", "none");
  afterEl.style.opacity = isBefore ? "0" : "1";
  beforeEl.style.opacity = isAfter ? "0" : "1";
}
