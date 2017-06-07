# identify the fill front
# computer priorities
# find patch with maximum priority
# find the patch with the highest similarity
# copy data from one patch to the other
# update confidence term

import numpy as np
import cv2 as cv
import argparse, os, sys
import Queue
from patch import *

class Inpainting:

    def __init__(self, source, mask, patchRadius):
        self.source = source
        self.mask = mask
        self.fillFront = None
        self.confidence = None
        self.boundary = None
        self.filled = np.uint8(self.mask > 0) * 255
        self.unfilled = np.uint8(self.mask == 0) * 255
        self.iteration = 0
        self.patchRadius = patchRadius
        self.inpainted = self.source.copy()
        for i in range(0,3):
            self.inpainted[:,:,i] *= (self.filled > 0)
        _, boundaries, _ = cv.findContours(self.unfilled, cv.RETR_LIST, cv.CHAIN_APPROX_NONE)
        self.boundaryIterator = iter(boundaries)
        self.confidence = np.zeros_like(self.filled, dtype=np.uint8)
        self.confidence[self.filled == 255] = 1
        self.initializeDatabase()

    def inpaint(self):
        try:
            # Initalize fill front
            self.boundary = self.boundaryIterator.next()
            self.fillFront = np.zeros_like(self.filled, dtype=np.uint8)
            self.fillFront = cv.drawContours(self.fillFront, self.boundary, -1, 255)

            # Initalize fill front patches
            self.deltaOmega = Queue.PriorityQueue()
            for coords in self.boundary:
                p = Patch((coords[0][1], coords[0][0]), self.patchRadius, self.inpainted, self.confidence, self.filled, self.fillFront)
                self.deltaOmega.put(p)
        except StopIteration:
            return True

        # Get patch with highest priority and match it
        while (not self.deltaOmega.empty()):

            # 2a) Find the patch with the maximum priority
            psi = self.deltaOmega.get()

            # 2b) Find the exemplar that minimizes the SSD
            bestRow, bestCol = self.match(psi)
            psiMatch = Patch((bestRow, bestCol), self.patchRadius, self.inpainted, self.confidence, self.filled, self.fillFront)
            # self.drawPatch(psi, psiMatch)

            # 2c) Copy image data from the matching patch
            psi.setWindow(psiMatch.getWindow(psiMatch.getImage()), self.inpainted, psi.valid(psiMatch))

            # 3) Update confidence
            psi.setWindow(psi.valid(psiMatch) * psi.getC(), self.confidence, psi.valid(psiMatch))

            # Update set of unfilled pixels
            psi.setWindow(255 * np.ones_like(psi.getWindow(psi.getFilled())), self.filled, np.ones((psi.getSize(), psi.getSize())))

            # Update fill front
            psi.setWindow(np.zeros_like(psi.getWindow(psi.getFilled())), self.fillFront, np.ones((psi.getSize(), psi.getSize())))
            borderCoords = psi.outerBorderCoords(self.inpainted)

            addToFillFront = lambda x: (self.fillFront[x[0],x[1]] == 0 and self.filled[x[0],x[1]] == 0)
            newFillFrontCoords = filter(addToFillFront, borderCoords)

            for rowcol in newFillFrontCoords:
                row, col = rowcol
                self.fillFront[row, col] = 255
                newPsi = Patch((row, col), self.patchRadius, self.inpainted, self.confidence, self.filled, self.fillFront)
                self.deltaOmega.put(newPsi)

            # Recompute confidence and priority of patches on fill front
            tempQueue = Queue.PriorityQueue()
            while (not self.deltaOmega.empty()):
                try:
                    tempPsi = self.deltaOmega.get()
                    row, col = tempPsi.getCoords()
                    if self.filled[row, col]:
                        pass
                    else:
                        tempPsi.setImage(self.inpainted)
                        tempPsi.setConfidence(self.confidence)
                        tempPsi.setFilled(self.filled)
                        tempPsi.setFillFront(self.fillFront)
                        tempPsi.computePriority()
                        tempQueue.put(tempPsi)
                except Queue.Empty:
                    break
            self.deltaOmega = tempQueue
            self.iteration += 1
            print("Done iteration %d" % (self.iteration))
        print("Done")
        return False

    def initializeDatabase(self):
        assert len(self.inpainted.shape) == 3
        assert self.inpainted.shape[0] == self.filled.shape[0]
        assert self.inpainted.shape[1] == self.filled.shape[1]

        patchSize = self.patchRadius * 2 + 1
        kernel = np.ones((patchSize, patchSize))
        channels = self.inpainted.shape[2]

        validRows = self.inpainted.shape[0] - 2 * self.patchRadius
        validCols = self.inpainted.shape[1] - 2 * self.patchRadius

        v = self.filled.copy()
        v[v == 255] = 1
        validFilled = cv.erode(v, kernel, iterations=1)
        validBorder = np.zeros_like(validFilled)
        validBorder[self.patchRadius:self.patchRadius+validRows, self.patchRadius:self.patchRadius+validCols] = 1
        valid = validBorder * validFilled
        validIndices = np.argwhere(valid == 1)
        self.patchIndices = validIndices

        patchDB = np.zeros((len(validIndices), (np.square(patchSize) * channels)), dtype=np.uint8)
        for i in range(len(validIndices)):
            row, col = validIndices[i]
            patchDB[i,:] = self.inpainted[row-self.patchRadius:row+self.patchRadius+1,col-self.patchRadius:col+self.patchRadius+1,:].flatten()
        self.patchDatabase = patchDB

    def match(self, patch):
        windowVector = patch.getWindow(patch.getImage()).flatten()[np.newaxis,:]
        t = self.patchDatabase.copy()
        t[:,windowVector[0] == 0] = 0
        ssd = t - 1.*windowVector
        sq = np.square(ssd)
        su = np.sum(sq, axis=1)
        m = np.argmin(su)
        return self.patchIndices[m]

    # def match(self, patch):
    #     window = patch.getWindow(patch.getImage()).astype(np.float32)
    #     row, col = self.patchIndices[0]
    #     ref = self.patchDatabase[row-self.patchRadius:row+self.patchRadius+1,col-self.patchRadius:col+self.patchRadius+1,:].astype(np.float32)
    #     ref[window == 0] = 0
    #     smallest = np.sum(np.square(window - ref))
    #     smallest_index = 0
    #     for i in range(1, len(self.patchIndices)):
    #         row, col = self.patchIndices[i]
    #         ref = self.patchDatabase[row-self.patchRadius:row+self.patchRadius+1,col-self.patchRadius:col+self.patchRadius+1,:].astype(np.float32)
    #         ref[window == 0] = 0
    #         ssd = np.sum(np.square(window - ref))
    #         if ssd < smallest:
    #             smallest = ssd
    #             smallest_index = i
    #     return self.patchIndices[smallest_index]

    def getInpainted(self):
        return self.inpainted

    def getFilled(self):
        return self.filled

    def getFillFront(self):
        return self.fillFront

    def getConfidence(self):
        return self.confidence

    def drawPatch(self, patch, other):
        row, col = patch.getCoords()
        radius = patch.getRadius()
        image = self.inpainted.copy()
        image[row - radius: row + radius, col - radius, 2] = 255
        image[row - radius: row + radius, col + radius, 2] = 255
        image[row - radius, col - radius : col + radius, 2] = 255
        image[row + radius, col - radius : col + radius, 2] = 255
        if other:
            orow, ocol = other.getCoords()
            oradius = other.getRadius()
            image[orow - oradius: orow + oradius, ocol - oradius, 1] = 255
            image[orow - oradius: orow + oradius, ocol + oradius, 1] = 255
            image[orow - oradius, ocol - oradius : ocol + oradius, 1] = 255
            image[orow + oradius, ocol - oradius : ocol + oradius, 1] = 255
        debug(image)


def readSource(fileName):
    try:
        source = cv.imread(fileName, 1)
    except:
        print("[ERROR] Source must be a color uint8 image")
        return None
    return source

def readMask(fileName):
    try:
        mask = cv.imread(fileName, 0)
    except:
        print("[ERROR] Alpha must be a grayscale uint8 image")
        return None
    return mask

def writeImage(fileName, image):
    try:
        cv.imwrite(fileName, image)
        success = True
    except:
        success = False
    return success

def debug(image):
    cv.imshow('image', image)
    cv.waitKey(0)
    cv.destroyAllWindows()

def main(args):
    source = readSource(args.s)
    mask = readMask(args.m)
    assert source is not None
    assert mask is not None

    inpainting = Inpainting(source, mask, args.r)
    done = False
    while not done:
        done = inpainting.inpaint()
    debug(inpainting.getInpainted())
    writeImage(args.o, inpainting.getInpainted())

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-s',
                        type=str,
                        help='Path to source image',
                        required=True)
    parser.add_argument('-m',
                        type=str,
                        help='Path to alpha image',
                        required=True)
    parser.add_argument('-o',
                        type=str,
                        help='Path to output image',
                        required=True)
    parser.add_argument('-r',
                        type=int,
                        help='Patch radius',
                        required=True)
    args = parser.parse_args()

    t1 = t2 = 0
    t1 = cv.getTickCount()
    main(args)
    t2 = cv.getTickCount()
    print('Completed in %g seconds'%((t2-t1)/cv.getTickFrequency()))