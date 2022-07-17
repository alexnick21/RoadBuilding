# -*- coding: utf-8 -*-
from qgis.core import (
  QgsApplication,
  QgsDataSourceUri,
  QgsCategorizedSymbolRenderer,
  QgsClassificationRange,
  QgsPointXY,
  QgsProject,
  QgsExpression,
  QgsField,
  QgsFields,
  QgsFeature,
  QgsFeatureRequest,
  QgsFeatureRenderer,
  QgsGeometry,
  QgsGraduatedSymbolRenderer,
  QgsMarkerSymbol,
  QgsMessageLog,
  QgsRectangle,
  QgsRendererCategory,
  QgsRendererRange,
  QgsSymbol,
  QgsVectorDataProvider,
  QgsVectorLayer,
  QgsVectorFileWriter,
  QgsWkbTypes,
  QgsSpatialIndex,
  QgsVectorLayerUtils,
  QgsPoint,
)

from qgis.core.additions.edit import edit

from qgis.PyQt.QtCore import *

from qgis.PyQt.QtGui import (
    QColor,
)
from qgis.PyQt.QtWidgets import QAction,QMessageBox
import processing

# Класс для построения дороги сети
class RoadBuild:
    def __init__(self):
        self.line_segments = []
        self.segment_names = []
        self.data = []

    def updateArea(self,ID,area):
        for line in self.data:
            if line[0] == ID:
                line[3] = area
                break

    ### Создаем дороги и все, что с ними связано ###
    # point_layer - Слой "крафтовых" точек
    # lines_name  - Имя для линейного слоя
    # buffer_size - Размер буфера в единицах проекта
    def createRoads(self, point_layer, lines_name, buffer_size):
        begin_points = []
        begin_points_num = []
        end_points   = []
        end_points_num   = []
        features = point_layer.getFeatures()
        if point_layer.featureCount() < 2:
            QMessageBox.warning(None, u"Ошибка", u'В слое точек кисло с точками!')
            return

        # Убьем временные слои, если они есть
        # Прочь с дороги!
        layers = QgsProject.instance().mapLayersByName(lines_name)            
        if len(layers) != 0:
           layer_lines = layers[0]
           QgsProject.instance().removeMapLayer(layer_lines.id())
           
        layers = QgsProject.instance().mapLayersByName("Buffered")            
        if len(layers) != 0:
           layer_buffer= layers[0]
           QgsProject.instance().removeMapLayer(layer_buffer.id())
        
        # дербаним точки
        # создадим служебные списки для обработки
        idi = 1
        for feature in features:
            geom = feature.geometry()
            geomSingleType = QgsWkbTypes.isSingleType(geom.wkbType())
            if geom.type() == QgsWkbTypes.PointGeometry:
                if geomSingleType:
                    #Все правильно, можно колбасить
                    begin_points.append(geom.asPoint())
                    begin_points_num.append(idi)
                    end_points.append(geom.asPoint())
                    end_points_num.append(idi)
                else:
                    QMessageBox.warning(None, u"Ошибка", u'В слое точек что-то не так с геометрией!')
                    return
                
            idi = idi + 1

        # Построим "дороги"
        # СОеденяем все и со всем по кратчайшему пути
        # Анализ рельефа остается только в рамках
        # вычисления длин наклонных линий и поправке к площади проекции
        for pb, bi in zip(begin_points, begin_points_num):
            for pe, ei in zip(end_points, end_points_num):
                poline = QgsGeometry.fromPolylineXY([pb, pe])
                if poline.length() != 0:
                    self.line_segments.append(poline)
                    self.segment_names.append(str(bi) + '-' + str(ei))
                
            end_points.pop(0)
            end_points_num.pop(0)
            
        #layerType = layer.type()
        #if layerType == QgsMapLayer.VectorLayer:
           # do some stuff here
           
        # Создадим в памяти слой
        # Сразу запихаем его в правильную систему координат дабы не искать его в Японии
        crs = QgsProject.instance().crs()
        layer = QgsVectorLayer('LineString?crs=epsg:' + str(crs.authid()), lines_name , 'memory') #?crs=epsg:4326
        layer.setCrs(crs) # Он с первого раза не понял :)
        prov = layer.dataProvider()
        layer.startEditing()
        res = prov.addAttributes([QgsField("ID", QVariant.Int), QgsField("segment", QVariant.String)])      
        
        idi = 1
        for pol, nm in zip(self.line_segments, self.segment_names):
            feat = QgsFeature()
            feat.setAttributes([idi,nm])
            feat.setGeometry(pol)
            prov.addFeatures([feat])
            self.data.append([idi,nm,pol.length(),0.0])
            idi = idi + 1
            
        layer.commitChanges()
        layer.updateExtents()
        
        # формируем буфера дорог
        # жутко неудобно они формируются, но уж как есть    
        QgsProject.instance().addMapLayers([layer])
        processing.runAndLoadResults("native:buffer", {'INPUT': layer,
               'DISTANCE': buffer_size,
               'SEGMENTS': len(self.line_segments),
               'DISSOLVE': False,
               'END_CAP_STYLE': 0,
               'JOIN_STYLE': 0,
               'MITER_LIMIT': 10,
               'OUTPUT': 'memory:buffer'})

        # Буфера надо спроецировать домой, а то что им в Японии мучаться
        layers = QgsProject.instance().mapLayersByName("Buffered")            
        if len(layers) != 0:
           layer_buffer= layers[0]
           layer_buffer.setCrs(crs)

           # Выясним и запомним площади
           feats = layer_buffer.getFeatures()
           for feat in feats:
               g = feat.geometry()
               fi = layer_buffer.fields().indexFromName('ID')
               fid = feat.attributes()[fi]
               self.updateArea(fid,g.area())
            
                
        return self.data
