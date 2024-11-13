"""
Code for subsetting a large polygon into smaller areas
This is intended to be used to subset a large area like the ACT into sub-sections that can then be downloaded and proceesed using the main.sh scripts in https://github.com/johnburley3000/PaddockTS/

Steps to use:
1. In QGIS, create a new square polygon layer as a geopackage:
   * Layer → Create Layer → New GeoPackage Layer
   * Set Databse name and layer name to the same thing
   * Geometry type: Polygon
   * ESPG:7855 (For ACT-related projects)
   * OK to create the layer
2. Right click on newly created layer and Toggle Editing (pencil icon)
    * In the toolbar, click on the green blob to toggle creating a new polygon.
       - If you don't see an option for the polygon (you amy only see a line option), right click on any icon on the toolbar and make sure the "Shape Digitizing Toolbar" is selected
       - Set you polygon type to rectangular (this code is assuming the polygon it is subsetting is a rectangle)
   * Click on the map, drag to create your polygon and then right-click to complete. Hi ok for "fid autogenerate"
   * Right-click on the layer and turn off editing and select Save to save the changes

3. Open the Processing Toolbox (Ctl+Alt+T) 
  * Click on the Python icon and select "Add script to Toolbox"
  * Select this python script

4. Once added, this script will show up under a "Grid Tools" folder

5. Running the script:
  * Choose the layer you want to subset (this will be the layer you just made)
  * Select how many columns (sub-regions) you want. 
  * How it works:
      - Since the main.sh code just takes a lat/long and angualr "buffer" variable, this code takes the number of columns 
        you want and uses that to calculate the buffer size for cells of that width. This buffer is then used to calculate the 
        height of each cell and the large geomtry is broken into this many rows and columns.
      - Once this is complete, if you select any of the new cells in the new layer, the info box will provide 
        the center point lat/long as and "buffer" values which you can paste into main.sh

NOTES:
  * If you make changes to the script by directly editing it in QGIS, these often don't propagate to script in the toolbox, 
     so you may want to assure the code is working as you want it first, before adding it.
  * Deleting the script in the Toolbox to reload it will actually delete the script file as well, so make sure you have a backup copy of the .py file

"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing, QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterFeatureSink,
                       QgsFeature, QgsGeometry, QgsWkbTypes,
                       QgsRectangle, QgsFeatureSink, QgsField,
                       QgsPointXY, QgsDistanceArea,
                       QgsProject)
from PyQt5.QtCore import QVariant
import math

class BoundingBoxDivider(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    COLUMNS = 'COLUMNS'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                'Input bounding box',
                [QgsProcessing.TypeVectorPolygon]
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.COLUMNS,
                'Number of Columns',
                QgsProcessingParameterNumber.Integer,
                defaultValue=2,
                minValue=1
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                'Output grid'
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        num_columns = self.parameterAsInt(parameters, self.COLUMNS, context)

        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))

        # Create output fields
        fields = source.fields()
        fields.append(QgsField('cell_id', QVariant.Int))
        fields.append(QgsField('cell_name', QVariant.String))
        fields.append(QgsField('row', QVariant.Int))
        fields.append(QgsField('col', QVariant.Int))
        fields.append(QgsField('center_lat', QVariant.Double))
        fields.append(QgsField('center_lon', QVariant.Double))
        fields.append(QgsField('buffer', QVariant.Double))
        fields.append(QgsField('notes', QVariant.String))

        # Get the sink
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            fields,
            QgsWkbTypes.Polygon,
            source.sourceCrs()
        )

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        # Get the bounding box
        for input_feature in source.getFeatures():
            bbox = input_feature.geometry().boundingBox()

            x_min = bbox.xMinimum()
            y_min = bbox.yMinimum()
            x_max = bbox.xMaximum()
            y_max = bbox.yMaximum()

            # Calculate column width in degrees
            width_degrees = (x_max - x_min) / num_columns

            # Calculate the width in meters at the middle latitude
            mid_lat = (y_max + y_min) / 2

            # Setup distance calculator
            distance_calc = QgsDistanceArea()
            distance_calc.setEllipsoid('WGS84')

            # Calculate width in meters at the middle latitude
            point1 = QgsPointXY(x_min, mid_lat)
            point2 = QgsPointXY(x_min + width_degrees, mid_lat)
            width_meters = distance_calc.measureLine([point1, point2])

            # Calculate height in degrees based on the width
            height_degrees = abs(width_degrees)

            # Calculate number of rows needed
            total_height = y_max - y_min
            num_rows = math.ceil(total_height / height_degrees)

            # Create grid
            cell_id = 1
            total = num_rows * num_columns
            current = 0

            for row in range(num_rows):
                if feedback.isCanceled():
                    break

                for col in range(num_columns):
                    # Calculate cell coordinates
                    cell_x_min = x_min + (col * width_degrees)
                    cell_x_max = cell_x_min + width_degrees
                    cell_y_min = y_min + (row * height_degrees)
                    cell_y_max = cell_y_min + height_degrees

                    # Calculate center point
                    center_x = (cell_x_min + cell_x_max) / 2
                    center_y = (cell_y_min + cell_y_max) / 2

                    # Calculate buffer (half width in degrees)
                    buffer = width_degrees / 2

                    # Generate cell name
                    cell_name = f"R{row+1:02d}C{col+1:02d}"

                    # Create rectangle geometry
                    rect = QgsRectangle(cell_x_min, cell_y_min,
                                        cell_x_max, cell_y_max)
                    geometry = QgsGeometry.fromRect(rect)

                    # Create feature
                    feature = QgsFeature(fields)
                    feature.setGeometry(geometry)

                    # Create attributes dictionary
                    attrs = {
                        'cell_id': cell_id,
                        'cell_name': cell_name,
                        'row': row + 1,
                        'col': col + 1,
                        'center_lat': round(center_y, 6),
                        'center_lon': round(center_x, 6),
                        'buffer': round(buffer, 6),
                        'notes': ""
                    }

                    # Map attributes to field indices
                    attribute_values = [attrs.get(f.name(), None) for f in fields]
                    feature.setAttributes(attribute_values)

                    # Add feature to sink
                    sink.addFeature(feature, QgsFeatureSink.FastInsert)

                    cell_id += 1
                    current += 1
                    feedback.setProgress(100 * current / total)


        return {self.OUTPUT: dest_id}

    def name(self):
        return 'divideboundingbox'

    def displayName(self):
        return 'Divide Bounding Box into Geographic Grid (buffered)'

    def group(self):
        return 'Grid Tools'

    def groupId(self):
        return 'gridtools'

    def createInstance(self):
        return BoundingBoxDivider()
