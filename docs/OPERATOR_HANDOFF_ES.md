# Guia Operativa - Primeros 5 Minutos

## Objetivo

Usar el mapa para ubicar rapidamente poligonos oficiales de daño de Copernicus EMSR884, priorizar inspeccion y compartir coordenadas/exportaciones con equipos de respuesta.

## Como usarlo

1. Abra la app y confirme que el AOI activo sea un AOI operativo de Venezuela, no el demo xBD.
2. Use el selector de AOI para cambiar entre `AOI02 Caracas` y `AOI06 Moron`.
3. Revise los indicadores:
   - `estructuras`: numero de poligonos built-up en el AOI.
   - `destruidos/dañados oficiales`: suma de `Destroyed` + `Damaged` segun EMS.
   - `posibles oficiales`: `Possibly damaged` segun EMS.
4. Use filtros:
   - `Todos`: todos los poligonos EMS.
   - `Destruido/Dañado`: solo `Destroyed` + `Damaged`.
   - `Revisado VLM`: solo elementos con revision VLM, si existe.
5. En `Prioridad`, haga click en un elemento. El mapa centra el poligono a zoom 18 y abre el popup.
6. Use el link `Google Maps` para compartir la ubicacion con equipos de campo.
7. Descargue CSV, GeoJSON o KML para analisis externo, QGIS, Google Earth o tableros.

## Confianza del Dato

- Las etiquetas vectoriales oficiales de Copernicus EMS son la fuente principal para AOI02/AOI06.
- `Destroyed` y `Damaged` se tratan como daño confirmado por el producto EMS.
- `Possibly damaged` se muestra por separado. No debe contarse como destruido/dañado confirmado.
- VLM, si aparece, es evidencia auxiliar para priorizar revision; no reemplaza EMS ni validacion humana.

## No Sobreafirmar

- Los features EMS `builtUpA` pueden no representar un edificio individual cada uno.
- Las etiquetas oficiales EMS son la fuente principal de verdad para este paquete.
- VLM y etiquetas inferidas son ayudas de triage, no confirmacion oficial.
- La ausencia de un poligono marcado no prueba que no haya daño.

## Limitaciones Conocidas

- AOI02/AOI06 validan la ruta vectorial EMS, pero no incluyen imagen antes/despues en el mapa.
- Los poligonos `builtUpA` son features oficiales de evaluacion built-up; no siempre equivalen a un edificio individual.
- Para AOIs grandes puede ser necesario convertir GeoJSON a PMTiles/vector tiles.
- La Guaira/AOI12 aun depende de que Copernicus publique el ZIP GRA.

## Cuando AOI12 Este Disponible

1. Descargar el ZIP GRA oficial de AOI12.
2. Ejecutar el importador EMS.
3. Revisar conteos contra summary table/PDF.
4. Copiar CSV/GeoJSON/KML/metadata a `public/data/aoi/emsr884-aoi12-caraballeda`.
5. Agregar AOI12 al catalogo.
6. Correr QA de navegador.
7. Publicar paquete estatico en Vercel.
