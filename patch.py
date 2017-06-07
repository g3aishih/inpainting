import numpy as np
import cv2 as cv

class Patch:

    def __init__(self, coords, radius, image, confidence, filled, fillFront):
        self.coords = coords
        self.radius = radius
        self.size = 2 * radius + 1
        self.P = None
        self.C = None
        self.D = None
        self.normal = [None, None]
        self.gradient = [None, None]
        self.alpha = 255
        self.image = image
        self.confidence = confidence
        self.filled = filled
        self.fillFront = fillFront
        self.computePriority()

    def computeConfidence(self):
        patchConfidence = self.getWindow(self.confidence)
        patchFilled = self.getWindow(self.filled)
        patchFiltered = patchConfidence[patchFilled == 255]
        if patchFiltered.size == 0:
            self.C = 0
        else:
            self.C = np.sum(patchFiltered) / (1.0 * patchFiltered.size)

    def computeGradient(self):
        patchGray = cv.cvtColor(self.getWindow(self.image), cv.COLOR_BGR2GRAY)

        Dy = cv.Sobel(patchGray, cv.CV_32F, 0, 1, ksize=-1)[self.radius][self.radius]
        Dx = cv.Sobel(patchGray, cv.CV_32F, 1, 0, ksize=-1)[self.radius][self.radius]

        Gy = -Dx
        Gx = Dy
        self.gradient = [Gy, Gx]

    def computeNormal(self):
        patchFillFront = self.getWindow(self.fillFront)

        Dy = cv.Sobel(patchFillFront, cv.CV_32F, 0, 1, ksize=-1)[self.radius][self.radius]
        Dx = cv.Sobel(patchFillFront, cv.CV_32F, 1, 0, ksize=-1)[self.radius][self.radius]

        mag = np.sqrt(np.square(Dy) + np.square(Dx))
        if mag != 0:
            Dx /= mag
            Dy /= mag
        Ny = -Dx
        Nx = Dy
        self.normal = [Ny, Nx]

    def computeData(self):
        self.computeNormal()
        self.computeGradient()
        self.D = np.abs(np.dot(self.normal, self.gradient)) / self.alpha

    def computePriority(self):
        self.computeConfidence()
        self.computeData()
        self.P = -1.0 * self.C * self.D

    def getWindow(self, data):
        if len(data.shape) == 2:
            image = data[:,:,None]
        else:
            image = data
        row, col = self.coords
        window = np.full((self.size, self.size, image.shape[2]), 0, dtype=image.dtype)
        if row - self.radius < 0:
            dRow = self.radius - row
            nRow = self.size - dRow
            sRow = 0
        else:
            dRow = 0
            nRow = self.size
            sRow = row - self.radius
        if row + self.radius >= self.image.shape[0]:
            nRow -=((row + self.radius + 1) - self.image.shape[0])

        if col - self.radius < 0:
            dCol = self.radius - col
            nCol = self.size - dCol
            sCol = 0
        else:
            dCol = 0
            nCol = self.size
            sCol = col - self.radius
        if col + self.radius >= image.shape[1]:
            nCol -= ((col + self.radius + 1) - image.shape[1])

        window[dRow : dRow + nRow, dCol : dCol + nCol, :] = image[sRow : sRow + nRow, sCol : sCol + nCol, :]
        return np.squeeze(window)

    def setWindow(self, source_data, destination_data, condition):
        row, col = self.coords

        if len(source_data.shape) == 2:
            source = source_data[:,:,None]
        else:
            source = source_data
        if len(destination_data.shape) == 2:
            destination = destination_data[:,:,None]
        else:
            destination = destination_data

        if row - self.radius < 0:
            sRow = self.radius - row
            nRow = source.shape[0] - sRow
            dRow = 0
        else:
            sRow = 0
            nRow = source.shape[0]
            dRow = row - self.radius
        if row + self.radius >= destination.shape[0]:
            nRow -= ((row + self.radius + 1) - destination.shape[0])

        if col - self.radius < 0:
            sCol = self.radius - col
            nCol = source.shape[1] - sCol
            dCol = 0
        else:
            sCol = 0
            nCol = source.shape[1]
            dCol = col - self.radius
        if col + self.radius >= destination.shape[1]:
            nCol -= ((col + self.radius + 1) - destination.shape[1])

        for c in range(0, destination.shape[2]):
            dPixels = np.squeeze(destination[dRow : dRow + nRow, dCol : dCol + nCol, c])
            sPixels = np.squeeze(source[sRow : sRow + nRow, sCol : sCol + nCol, c])
            cPixels = condition[sRow : sRow + nRow, sCol : sCol + nCol]
            dPixels[cPixels > 0] = sPixels[cPixels > 0]
            destination[dRow : dRow + nRow, dCol : dCol + nCol, c] = dPixels

    def getCoords(self):
        return self.coords

    def getRadius(self):
        return self.radius

    def getSize(self):
        return self.size

    def getImage(self):
        return self.image

    def getFilled(self):
        return self.filled

    def getC(self):
        return self.C

    def getD(self):
        return self.D

    def getP(self):
        return self.P

    def setConfidence(self, confidence):
        self.confidence = confidence

    def setFillFront(self, fillFront):
        self.fillFront = fillFront

    def setFilled(self, filled):
        self.filled = filled

    def setImage(self, image):
        self.image = image

    def __cmp__(self, other):
        return cmp(self.P, other.P)

    def __repr__(self):
        return "Coords: %s\nPriority: %s\nConfidence: %s\nData: %s\nNormal: %s\nGradient: %s\n" % (str(self.coords), str(self.P), str(self.C), str(self.D), str(self.normal), str(self.gradient))

    def valid(self, other):
        return np.logical_and(self.getWindow(self.filled) == 0, other.getWindow(other.filled) > 0)

    def outerBorderCoords(self, image):
        wo = self.radius + 1
        row, col = self.coords
        rows = np.arange(row-wo,row+wo+1)
        rowplus = np.full_like(rows,row+wo)
        rowminus = np.full_like(rows,row-wo)
        # we don't want the same coords appearing twice so the
        # horizontal outer boundary contains one less pixel
        cols = np.arange(col-wo,col+wo)
        colplus = np.full_like(cols,col+wo)
        colminus = np.full_like(cols,col-wo)
        borderCoords =  (zip(rows,colplus) +
                         zip(rowplus,cols) +
                         zip(rows,colminus) +
                         zip(rowminus,cols))
        withinLimits = lambda x: ((x[0]<image.shape[0]) and
                                (x[0]>=0) and
                                (x[1]<image.shape[1]) and
                                (x[1]>=0))
        return filter(withinLimits, borderCoords)