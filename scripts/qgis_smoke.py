"""Run in the QGIS Python console after installing/enabling this plugin.

exec(open(r'C:/path/QueryGIS_with_Codex/scripts/qgis_smoke.py', encoding='utf-8').read())
Only the uniquely named memory layers created by this check are removed afterwards.
"""
import math
import threading
import uuid
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY
from qgis.utils import plugins

plugin = plugins.get("querygis_with_codex")
if plugin is None:
    raise RuntimeError("Enable QueryGIS with Codex before running this check")
project = QgsProject.instance()
tag = "__QueryGIS_Codex_smoke_" + uuid.uuid4().hex
source = QgsVectorLayer("Point?crs=EPSG:5179", tag + "_input", "memory")
feature = QgsFeature()
feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1000000, 2000000)))
source.dataProvider().addFeatures([feature])
source.updateExtents()
project.addMapLayer(source)
try:
    code = """
source = QgsProject.instance().mapLayer(%r)
result = processing.run('native:buffer', {
    'INPUT': source, 'DISTANCE': 500, 'SEGMENTS': 16,
    'END_CAP_STYLE': 0, 'JOIN_STYLE': 0, 'MITER_LIMIT': 2,
    'DISSOLVE': False, 'OUTPUT': 'TEMPORARY_OUTPUT'
})
output = result['OUTPUT']
output.setName(%r)
QgsProject.instance().addMapLayer(output)
print('500m buffer created')
""" % (source.id(), tag + "_output")
    result = plugin._execute_python(code, threading.Event())
    assert len(result["layers"]) == 1, result
    output = project.mapLayer(result["layers"][0]["id"])
    assert output.isValid() and output.featureCount() == 1
    assert output.crs().authid() == "EPSG:5179"
    area = next(output.getFeatures()).geometry().area()
    assert abs(area - math.pi * 500 ** 2) / (math.pi * 500 ** 2) < 0.02, area
    print("PASS: QueryGIS executed native:buffer, validated CRS/count/area, and restored processing.run")
finally:
    for layer in list(project.mapLayers().values()):
        if layer.name() in {tag + "_input", tag + "_output"}:
            project.removeMapLayer(layer.id())
