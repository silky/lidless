import zmstream
import cv
import math
import pprint
import os
import sys
import tempfile

class Percept :
	def image_jpegstr(self, jpeg_str) :
		# this isn't great but OpenCV's a bit of a jerk about loading images
		fn = tempfile.mktemp('.jpg')
		try :
			h = open(fn, 'w')
			h.write(jpeg_str)
			h.close()

			return cv.LoadImage(fn)
		finally :
			os.unlink(fn)

	def filter_edges(self, img) :
		sz = cv.GetSize(img)
		bw = cv.CreateMat(sz[1], sz[0], cv.CV_8U)
		med = cv.CreateMat(sz[1], sz[0], cv.CV_8U)
		canny = cv.CreateMat(sz[1], sz[0], cv.CV_8U)
		cv.CvtColor(img, bw, cv.CV_RGB2GRAY)
		cv.Smooth(bw, med, cv.CV_MEDIAN, 5)
		cv.Canny(med, canny, 75, 112, 3)
		return canny

	def dict_diff(self, d1, d2) :
		key_merge = set(d1.keys()).intersection(d2.keys())
		result = {}
		for k in key_merge :
			result[k] = abs(d1[k] - d2[k])
		return result
	
	def bin_edgecount(self, img, bins=4096) :
		sz = cv.GetSize(img)
		twi = sz[1]
		thi = sz[0]
		tw = float(twi)
		th = float(thi)
		ta = tw * th
		r = tw/th
		a = ta / bins
		h = int(math.pow(a / r, 0.5))
		w = int(a / h)

		# bin maximums, integer rounded
		wbm = twi / w
		hbm = thi / h
		whitecounts = {}
		for wb in range(wbm) :
			for hb in range (hbm) :
				whitecounts[wb, hb] = 0

		for wo in range(wbm * w) :
			for ho in range(hbm * h) :
				# integer division for the counts, find bin numbers for current pixel
				b_w = wo / w
				b_h = ho / h
				v = img[wo, ho]
				if v > 0 :
					whitecounts[b_w, b_h] += 1

		return whitecounts

	def get_size_for_bin_images(self, bindict) :
		width = max([x for x,y in bindict.keys()]) + 1
		bins = len(bindict)
		height = bins / width
		return width, height

	def bins_to_img(self, bindict) :
		if not bindict :
			return None
		
		width, height = self.get_size_for_bin_images(bindict)

		img = cv.CreateMat(width, height, cv.CV_8U)
		# hardcode scaling
		scaling = 10
		# auto scaling
		#scaling = 255 / float(max(bindict.values()))

		print "wb %d hb %d sc %0.3f" % (width, height, scaling)

		for x,y in bindict :
			try :
				# scaled from maximum
				img[x,y] = min(255, int(scaling * float(bindict[x,y])))
				# clipped, shown direct difference
				#img[x,y] = min(255, bindict[x,y])
			except ZeroDivisionError :
				img[x,y] = 0
		return img

	def get_wh(self, img) :
		height, width = cv.GetSize(img)
		return width, height

	def create_image_matching_size(self, img, depth) :
		width, height = self.get_wh(img)
		img_out = cv.CreateMat(width, height, depth)
		return width, height, img_out

	def filter_for_blobs(self, img) :
		width, height, img_out = self.create_image_matching_size(img, cv.CV_8U)

		THRESHOLD = 80
		RATIO = .3
		KS = 5

		border = (KS - 1) / 2

		for x in range(0, width) :
			for y in range(0, height) :
				if x < border or x >= width - border or y < border or y >= height - border :
					img_out[x,y] = 0
				else :
					c = 0
					for xc in range(-border, border+1) :
						for yc in range(-border, border+1) :
							if img[xc+x, yc+y] >= THRESHOLD :
								c += 1
					if c >= RATIO * KS * KS :
						img_out[x,y] = 255
					else :
						img_out[x,y] = 0

		return img_out

	def frames_ago(self, motionframe, history) :
		MAX = 256 - 1

		if history is None :
			width, height, history = self.create_image_matching_size(motionframe, cv.CV_8U)
			for x in range(width) :
				for y in range(height) :
					history[x,y] = MAX
		else :
			width, height = self.get_wh(motionframe)

		for x in range(width) :
			for y in range(height) :
				if motionframe[x,y] > 0 :
					history[x,y] = 0
				else :
					if history[x,y] != MAX :
						history[x,y] += 5

		return history

if __name__ == '__main__' :
	p = Percept()
	url = sys.argv[1]
	streamer = zmstream.ZMStreamer(1, url)
	edge_bin = {}
	history = None
	for i in streamer.generate() :
		img = p.image_jpegstr(i)

		filtered = p.filter_edges(img)
		#cv.SaveImage('edges.png', filtered)

		new_bin = p.bin_edgecount(filtered)

		diff = p.dict_diff(new_bin, edge_bin)
		edge_bin = new_bin

		motion_image = p.bins_to_img(diff)
		if motion_image :
			blob_motion = p.filter_for_blobs(motion_image)
			#cv.SaveImage('motion.png', blob_motion)

			history = p.frames_ago(blob_motion, history)
			cv.SaveImage('cumulative.png', history)

		for k in diff :
			diff[k] = '=' * (diff[k] / 5)

		#pprint.pprint(diff)