import numpy as np
import pandas as pd 
from collections import Counter 

import pmbec 
from epitopes import amino_acid 


import sklearn.linear_model
import sklearn.svm 
import sklearn.ensemble
import sklearn.decomposition 

AMINO_ACID_LETTERS =list(sorted([
	'G', 'P',
	'A', 'V',
	'L', 'I',
	'M', 'C',
	'F', 'Y', 
	'W', 'H', 
	'K', 'R',
	'Q', 'N', 
	'E', 'D',
	'S', 'T',
]))

AMINO_ACID_PAIRS = ["%s%s" % (x,y) for y in AMINO_ACID_LETTERS for x in AMINO_ACID_LETTERS]

AMINO_ACID_PAIR_POSITIONS = dict( (y, x) for x, y in enumerate(AMINO_ACID_PAIRS))

def feature_dictionary_to_vector(dictionary):
	"""
	Takes a dictionary mapping from amino acid letter pairs (e.g. "AC"), 
	re-encodes the keys as indices
	"""
	vec = [None] * len(AMINO_ACID_PAIRS)
	for letter_pair, value in dictionary.iteritems():
		idx = AMINO_ACID_PAIR_POSITIONS[letter_pair]
		vec[idx] = value
	assert all(vi is not None for vi in vec) 
	return np.array(vec)


def encode_inputs(X_pair_indices, pairwise_feature_vec):
	"""
	X_pair_indices : 2d array
		Indices of amino acid combinations for each (peptide, allele pseudosequence) entry
	pairwise_features : dict
		Maps from AA pair indices to continuous values 
	""" 
	n_samples, n_dims = X_pair_indices.shape 

	assert len(pairwise_feature_vec) == (20*20)
	X_encoded = np.zeros((n_samples, n_dims), dtype=float)
	for row_idx, x in enumerate(X_pair_indices):
		for col_idx, xi in enumerate(x):
			X[row_idx, col_idx] = pairwise_feature_vec[xi]
	return X_encoded


def encode_pairwise_coefficients(peptide_seqs, mhc_seqs, model_weights):
	"""
	Re-encode sequences into a 20x20 AA pairwise feature matirx relative to some linear model model_weights
	"""
	assert all(len(s) == 9 for s in peptide_seqs)
	assert len(peptide_seqs) == len(mhc_seqs), "%d != %d" % (len(peptide_seqs), len(mhc_seqs))
	n_mhc_letters = len(mhc_seqs[0])
	assert all(len(s) == n_mhc_letters for s in mhc_seqs)
	assert len(model_weights) == (9 * n_mhc_letters), "model len %d != %d" % (len(model_weights), (9 * n_mhc_letters))
	

	n_dims = 20 * 20
	n_samples = len(peptide_seqs)
	coeffs = np.zeros((n_samples, n_dims), dtype=float)
	counts = Counter()
	for row_idx, peptide_seq in enumerate(peptide_seqs):
		allele_seq = mhc_seqs[row_idx]
		for i, peptide_letter in enumerate(peptide_seq):
			for j, mhc_letter in enumerate(allele_seq):
				key = "%s%s" % (peptide_letter, mhc_letter)
				counts[key] += 1
				col_idx = AMINO_ACID_PAIR_POSITIONS[key]
				weight_idx = i * 9 + j
				coeffs[row_idx, col_idx] += model_weights[weight_idx]
	print counts 
	assert False
	return coeffs

def estimate_pairwise_features(peptide_seqs, mhc_seqs, model_weights, Y):
	C = encode_pairwise_coefficients(peptide_seqs, mhc_seqs, model_weights)
	print C[0:10]
	print "Solving linear system..."
	feature_weights, _, _, _ = np.linalg.lstsq(C, Y)
	feature_dict = {}
	n_mhc_letters = mhc_seqs[0]
	for idx, v in enumerate(feature_weights):
		i = idx % 20
		j = idx / 20
		key = "%s%s" % (AMINO_ACID_LETTERS[i], AMINO_ACID_LETTERS[j])
		feature_dict[key] = v 
	return feature_dict


def generate_training_data(binding_data_filename = "mhc1.csv", mhc_seq_filename = "MHC_aa_seqs.csv"):
	df_peptides = pd.read_csv(binding_data_filename).reset_index()

	print "Loaded %d peptides" % len(df_peptides)

	df_peptides['MHC Allele'] = df_peptides['MHC Allele'].str.replace('*', '').str.strip()
	df_peptides['Epitope']  = df_peptides['Epitope'].str.strip().str.upper()

	print "Peptide lengths"
	print df_peptides['Epitope'].str.len().value_counts()


	mask = df_peptides['Epitope'].str.len() == 9
	mask &= df_peptides['IC50'] <= 10**6
	df_peptides = df_peptides[mask]
	print "Keeping %d peptides (length >= 9)" % len(df_peptides)


	groups = df_peptides.groupby(['MHC Allele', 'Epitope'])
	grouped_ic50 = groups['IC50']
	grouped_std = grouped_ic50.std() 
	grouped_count = grouped_ic50.count() 
	duplicate_std = grouped_std[grouped_count > 1]
	duplicate_count = grouped_count[grouped_count > 1]
	print "Found %d duplicate entries in %d groups" % (duplicate_count.sum(), len(duplicate_count))
	print "Std in each group: %0.4f mean, %0.4f median" % (duplicate_std.mean(), duplicate_std.median())
	
	df_peptides = grouped_ic50.median().reset_index()

	# reformat HLA allales 'HLA-A*03:01' into 'HLA-A0301'
	peptide_alleles = df_peptides['MHC Allele']
	peptide_seqs = df_peptides['Epitope']
	peptide_ic50 = df_peptides['IC50']
	
	print "%d unique peptide alleles" % len(peptide_alleles.unique())
	
	df_mhc = pd.read_csv(mhc_seq_filename)
	print "Loaded %d MHC alleles" % len(df_mhc)


	mhc_alleles = df_mhc['Allele'].str.replace('*', '')
	mhc_seqs = df_mhc['Residues']

	assert len(mhc_alleles) == len(df_mhc)
	assert len(mhc_seqs) == len(df_mhc)

	print list(sorted(peptide_alleles.unique()))
	print mhc_alleles[:20]
	print "%d common alleles" % len(set(mhc_alleles).intersection(set(peptide_alleles.unique())))
	print "Missing allele sequences for %s" % set(peptide_alleles.unique()).difference(set(mhc_alleles))

	mhc_seqs_dict = {}
	for allele, seq in zip(mhc_alleles, mhc_seqs):
		mhc_seqs_dict[allele] = seq 


	X = []
	W = []
	Y = []
	n_dims = 9 * len(mhc_seqs[0])
	for peptide_idx, allele in enumerate(peptide_alleles):
		if allele in mhc_seqs_dict:
			allele_seq = mhc_seqs_dict[allele]
			peptide = peptide_seqs[peptide_idx]
			n_letters = len(peptide)
			ic50 = peptide_ic50[peptide_idx]
			print peptide_idx, allele, peptide, allele_seq, ic50
			for start_pos in xrange(0, n_letters - 8):
				stop_pos = start_pos + 9
				vec = [AMINO_ACID_PAIR_POSITIONS[peptide_letter + mhc_letter] 
				       for peptide_letter in peptide[start_pos:stop_pos]
				       for mhc_letter in allele_seq]
				X.append(np.array(vec))
				Y.append(ic50)
				weight = 1.0 / (n_letters - 8)
				W.append(weight)
	X = np.array(X)
	W = np.array(W)
	Y = np.array(Y)

	print "Generated data shape", X.shape
	assert len(W) == X.shape[0]
	assert len(Y) == X.shape[0]
	return X, W, Y



class LogLinearRegression(sklearn.linear_model.LinearRegression):
	def fit(self, X, Y, sample_weight = None):
		#Y = np.minimum(1.0, np.maximum(0.0, 1.0 - np.log(Y)/ np.log(50000)))
		Y = np.log(Y)
		return sklearn.linear_model.LinearRegression.fit(self, X, Y)

	def predict(self, X):
		transformed_Y = sklearn.linear_model.LinearRegression.predict(self, X)
		#logY = -transformed_Y + 1.0
		#return 50000 ** logY
		return np.exp(transformed_Y)


class TwoPassRegressor(object):

	def __init__(self, classifier_threshold = 10**3):
		self.classifier_threshold = classifier_threshold
		
	def fit(self,X,Y,W=None):

		categories =  np.maximum(0, (np.log10(Y) / np.log10(50)).astype('int')) #Y <= self.classifier_threshold #
		print np.unique(categories)
		self.first_pass = sklearn.ensemble.RandomForestClassifier() #sklearn.linear_model.LogisticRegression()
		self.first_pass.fit(X,categories)
		
		Y = np.log(Y)
		self.regressors = [None] * (np.max(categories) + 1)
		for category in np.unique(categories):
			mask = categories == category
			regressor = sklearn.linear_model.RidgeCV()
			regressor.fit(X[mask], Y[mask])
			self.regressors[category] = regressor
		return self


	def predict(self, X):
		categories = self.first_pass.predict(X)

		combined = np.zeros_like(categories, dtype=float)
		
		for category in np.unique(categories):
			mask = categories == category
			pred = self.regressors[category].predict(X[mask])
			combined[mask] = pred 
		return np.exp(combined) 


"""
class Regressor(object):
	def __init__(self, initial_coefficients = None):
		if initial_coefficients is None:
			self.pairwise_features = pmbec.read_coefficients()
		else:
			self.pairwise_features = initial_coefficients 

	def fit(self, X, Y, sample_weight = None):

	def predict(self, X):
"""
def split(data, start, stop):
	if len(data.shape) == 1:
		train = np.concatenate([data[:start], data[stop:]])
	else:
		train = np.vstack([data[:start], data[stop:]])
	test = data[start:stop]
	return train, test 

def shuffle(X, Y, W):
	n = len(Y)
	indices = np.arange(n)
	np.random.shuffle(indices)
	X = X[indices]
	Y = Y[indices]
	W = W[indices]
	return X, Y, W

def load_training_data():
	print "Loading X"
	X = np.load("X.npy")
	print "Loading Y"
	Y = np.load("Y.npy")
	print "Loading W"
	W = np.load("W.npy")
	assert len(X) == len(Y)
	assert len(W) == len(Y)
	assert len(X.shape) == 2
	return X, Y, W

def save_training_data(X, Y, W):
	print "Saving to disk..."
	np.save("X.npy", X)
	np.save("W.npy", W)
	np.save("Y.npy", Y)

def cross_validation(X, Y, W, n_splits = 10):

	coeff = pmbec.read_coefficients()
	coeff_vec = feature_dictionary_to_vector(coeff)
	X = encode_inputs(X, coeff_vec)

	n_samples = len(Y)
	split_size = n_samples / n_splits
	
	errors = []
	accuracies = []
	sensitivities = []
	specificities = []
	for split_idx in xrange(n_splits):
		test_start = split_idx * split_size
		test_stop = min((split_idx + 1) * split_size, n_samples)
		print "Split #%d" % (split_idx+1), "n =",  n_samples - (test_stop - test_start)
		
		X_train, X_test = split(X, test_start, test_stop)



		assert len(X_train.shape) == len(X_test.shape)
		assert X_train.shape[1] == X_test.shape[1]
		Y_train, Y_test = split(Y, test_start, test_stop)
		W_train, W_test = split(W, test_start, test_stop)

		print "-- fitting regression model"
		model = LogLinearRegression()
		model.fit(X_train, Y_train, W_train)

		pred = model.predict(X_test)
		split_error = np.sum(np.abs(pred-Y_test) * W_test) / np.sum(W_test)
		errors.append(split_error)

		print "-- error:", split_error
		
		pred_lte = pred <= 500
		actual_lte = Y_test <= 500
		pred_gt = ~pred_lte 
		actual_gt = ~actual_lte 
		correct = (pred_lte & actual_lte) | (pred_gt & actual_gt)
		total_weights = np.sum(W_test)
		accuracy = np.sum(W_test * correct) / total_weights

		sensitivity = np.sum(W_test[actual_lte] * correct[actual_lte]) / np.sum(W_test[actual_lte])
		specificity = np.sum(W_test[pred_lte] * correct[pred_lte]) / np.sum(W_test[pred_lte])

		print "-- accuracy", accuracy 
		print "-- sensitivity", sensitivity 
		print "-- specificity", specificity
	print "Overall CV error", np.mean(errors)	
	return np.mean(errors)		



if __name__ == '__main__':
	
	import argparse
	parser = argparse.ArgumentParser(description='Generate training data for MHC binding prediction and use it to train regressors')
	parser.add_argument('--generate',  action='store_true', default=False)
	parser.add_argument('--fit', action='store_true', default=False)

	args = parser.parse_args()
	print "Commandline Args:"
	print args
	print 

	if args.generate:
		X,W,Y = generate_training_data()
		save_training_data(X, Y, Z)

	if args.fit:
		if "X" not in locals() or "Y" not in locals() or "W" not in locals():
			X, Y, W = load_training_data()

		X, Y, W = shuffle(X, Y, W)

		cross_validation(X,Y,W)