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
  QgsRaster
)

from qgis.core.additions.edit import edit

from qgis.PyQt.QtCore import *

from qgis.PyQt.QtGui import (
    QColor,
)
from qgis.PyQt.QtWidgets import QAction,QMessageBox
import processing
import math

# Класс для построения дороги сети
class RoadBuild:
    def __init__(self):
        self.line_segments = []
        self.segment_names = []
        self.segment_elev =  []
        self.data = []
        self.begin_points = []
        self.begin_points_num = []
        self.end_points   = []
        self.end_points_num   = []

    def segmentCount(self):
        return len(self.line_segments)

    # Проверка нахождения точки на проектной линии
    def hasTransitPoint(self, polyline, bp, ep):
        for p in self.begin_points:
            dist = polyline.distance( QgsGeometry.fromPointXY(p))
            if dist == 0 and not QgsGeometry.fromPointXY(p).equals(QgsGeometry.fromPointXY(bp)) and not QgsGeometry.fromPointXY(p).equals(QgsGeometry.fromPointXY(ep)):
                return True

        return False   

    # Получение информации о высоте точки
    # по данным растра
    def valueRaster(self, p, raster_layer):
        value = list(raster_layer.dataProvider().identify(p, QgsRaster.IdentifyFormatValue).results().values())[0]
        return value 

    # Обновление сведений о площади объекта
    def updateArea(self, ID, area):
        for line in self.data:
            if line[0] == ID:
                line[3] = area
                break

    ### Создаем дороги и все, что с ними связано ###
    # point_layer - Слой "крафтовых" точек
    # lines_name  - Имя для линейного слоя
    # buffer_size - Размер буфера в единицах проекта
    def createRoads(self, point_layer, lines_name, buffer_size, layer_relief):        
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
                    self.begin_points.append(geom.asPoint())
                    self.begin_points_num.append(idi)
                    self.end_points.append(geom.asPoint())
                    self.end_points_num.append(idi)
                else:
                    QMessageBox.warning(None, u"Ошибка", u'В слое точек что-то не так с геометрией!')
                    return
                
            idi = idi + 1

        # Построим "дороги"
        # СОеденяем все и со всем по кратчайшему пути
        # Анализ рельефа остается только в рамках
        # вычисления длин наклонных линий и поправке к площади проекции
        # реальную поверхность упрощаем т.к. задача очевидно не боевая
        for pb, bi in zip(self.begin_points, self.begin_points_num):
            for pe, ei in zip(self.end_points, self.end_points_num):
                poline = QgsGeometry.fromPolylineXY([pb, pe])
                # Встраиваем примитивную проверку на откровенно ненужные сегменты
                if poline.length() != 0 and not self.hasTransitPoint(poline, pb, pe):
                    self.segment_elev.append([self.valueRaster(pb, layer_relief), self.valueRaster(pe, layer_relief)])
                    self.line_segments.append(poline)
                    self.segment_names.append(str(bi) + '-' + str(ei))
                
            self.end_points.pop(0)
            self.end_points_num.pop(0)                    
           
        # Создадим в памяти слой
        # Сразу запихаем его в правильную систему координат дабы не искать его в Японии
        crs = QgsProject.instance().crs()
        layer = QgsVectorLayer('LineString?crs=epsg:' + str(crs.authid()), lines_name , 'memory') #?crs=epsg:4326
        layer.setCrs(crs) # Он с первого раза не понял :)
        prov = layer.dataProvider()
        layer.startEditing()
        res = prov.addAttributes([QgsField("ID", QVariant.Int),
                                  QgsField("segment", QVariant.String),
                                  QgsField("h", QVariant.Double),
                                  QgsField("incl", QVariant.Double),
                                  QgsField("L", QVariant.Double),
                                  QgsField("S", QVariant.Double)])      
        
        idi = 1
        for pol, nm, elevations in zip(self.line_segments, self.segment_names, self.segment_elev):
            feat = QgsFeature()
            
            # Вычисление превышения и угла наклона
            # Прибегаем к помощи теоремы Пифагора
            h = elevations[0] - elevations[1]
            # Учитываем общий наклон поверхности
            L = math.sqrt(abs(h)**2 + pol.length()**2)
            
            inclination = math.asin(abs(h) / L)
            
            feat.setAttributes([idi, nm, h , inclination, L, 0.0])
            feat.setGeometry(pol)
            prov.addFeatures([feat])
            
            self.data.append([idi,nm,L,0.0])
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
           layer_buffer = layers[0]
           layer_buffer.setCrs(crs)

           # Выясним и запомним площади        
           layer_buffer.startEditing()
           feats = layer_buffer.getFeatures()
           for feat in feats:
               g = feat.geometry()
               fi = layer_buffer.fields().indexFromName('ID')
               incli = layer_buffer.fields().indexFromName('incl')
               Si = layer_buffer.fields().indexFromName('S')
               
               fid = feat.attributes()[fi]
               incl = feat.attributes()[incli]
               
               # Корректируем площадь по углу наклона
               # Исходим из теоремы о площади проекции плоской фигуры
               S = g.area() / math.cos(incl)
               self.updateArea(fid, S)
               feat.setAttribute(Si,S)
               layer_buffer.updateFeature(feat)
               
           layer_buffer.commitChanges()
           layer_buffer.updateExtents()
                
        return self.data
