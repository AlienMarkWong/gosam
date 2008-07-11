#!/usr/bin/env python
# this file is part of gosam (generator of simple atomistic models) 
# Licence: GNU General Public License version 2
"""\
Coincidence Site Lattice related utilities.
"""
usage_string = """\
 Usage: 
   csl.py hkl         - list all CSL sigma up to 1000 with corresponding angle
                         example: csl.py 100
   csl.py hkl sigma   - details about CSL with given sigma
                         example: csl.py 111 31
"""

import sys
import functools
from math import degrees, atan, sqrt, pi
import numpy
from numpy import array, identity, dot, inner, cross
from numpy.linalg import inv, det, solve
from rotmat import rodrigues, print_matrix

def gcd(a, b):
    "Returns the Greatest Common Divisor"
    assert isinstance(a, int)
    assert isinstance(b, int)
    while a:
        a, b = b%a, a
    return b

def coprime(a, b):
    return gcd(a,b) in (0, 1)

def gcd_array(a):
    r = abs(a[0])
    for i in a[1:]:
        if i != 0:
            r = gcd(r, abs(i))
    return r

def cubic_csl(hkl, m, n):
    h,k,l = hkl
    assert coprime(h,k) and coprime(k,l) and coprime(h,l)
    sqsum = h*h + k*k + l*l
    assert sqsum > 0
    sigma = m*m + n*n * sqsum
    while sigma != 0 and sigma % 2 == 0:
        sigma /= 2
    if sigma == 1:
        return None, None
    if m > 0:
        theta = 2 * atan(sqrt(sqsum) * n / m)
    else:
        theta = pi
    return sigma, theta

def get_theta_m_n_list(hkl, sigma, verbose=False):
    if sigma == 1:
        return [(0., 0, 0)]
    thetas = []
    for m in range(50):
        for n in range(1, 50):
            if not coprime(m, n):
                continue
            s, theta = cubic_csl(hkl, m, n)
            if s == sigma:
                if verbose:
                    print "m=%i n=%i" % (m, n), "%.2f" % degrees(theta)
                thetas.append((theta, m, n))
    return thetas

def find_theta(hkl, sigma, verbose=True):
    thetas = get_theta_m_n_list(hkl, sigma, verbose=verbose)
    if thetas:
        return min(thetas, key= lambda x: x[0])


def _get_unimodular_transformation():
    "generator of a few possible unimodular transformations"
    # randomly choosen
    yield identity(3)
    yield array([[1, 0, 1],
                [0, 1, 0],
                [0, 1, 1]])
    yield array([[1, 0, 1], 
                [0, 1, 0], 
                [0, 1, -1]])
    yield array([[1, 0, 1], 
                [0, 1, 0], 
                [-1,1, 0]])
    yield array([[1, 0, 1], 
                 [1, 1, 0], 
                 [1, 1, 1]])


def _get_S():
    Sp = identity(3) # for primitive cubic
    Sb = array([[0.5, -0.5, 0],
                [0.5,  0.5, 0],
                [0.5,  0.5, 1]]) # body-centered cubic
    Sf = array([[0.5, 0.5, 0],
                [0,   0.5, 0.5],
                [0.5, 0,   0.5]]) # face-centered cubic
    # Sf doesn't work?
    return Sp


def transpose_3x3(f):
    """decorator; transpose the first argument and the return value (both 
    should be 3x3 arrays). This makes column operations easier"""
    @functools.wraps(f)
    def wrapper(*args, **kwds):
        args_list = list(args)
        assert args_list[0].shape == (3,3)
        args_list[0] = args_list[0].transpose()
        ret_val = f(*args_list, **kwds)
        assert ret_val.shape == (3,3)
        return ret_val.transpose()
    return wrapper


@transpose_3x3
def beautify_matrix(T):
    # We don't want to change the lattice. 
    # We use only elementary column operations that don't change det 
    def looks_better(a, b):
        x = numpy.abs(a)
        y = numpy.abs(b)
        #return x.sum() < y.sum()
        #return x.sum() < y.sum() or (x.sum() == y.sum() and x.max() < y.max())
        return x.max() < y.max()

    def try_add(a, b):
        changed = False
        while looks_better(a+b, a):
            a += b
            changed = True
        return changed

    def try_add_sub(a, b):
        return try_add(a, b) or try_add(a, -b)

    while True:
        changed = False
        for i in range(3):
            for j in range(3):
                if i != j and not changed:
                    changed = try_add_sub(T[i], T[j]) 
                    if changed:
                        break
        if not changed:
            break

    return T


@transpose_3x3
def make_parallel_to_axis(T, col, axis):
    """\
    T: matrix 3x3, i.e. 3 vectors, 2*T is integer matrix
    axis: vector (3)
    return value:
       matrix T is transformed using operations:
         - interchanging two columns
         - adding a multiple of one column to another, 
         - multiplying column by -1
       such that the result matrix has the same det 
                                and has first vector == axis
       the transformation is _not_ rotation
    """
    double_T = False
    if not is_integer(T):
        T *= 2 # make it integer, will be /=2 at the end
        double_T = True
    axis = array(axis)
    c = solve(T.transpose(), axis) # c . T == axis
    if not is_integer(c):
        mult = find_smallest_multiplier(c)
        c *= mult
    c = c.round().astype(int)
    #print "c", c
    ##assert 1 in numpy.abs(c), c # it may not be true?
    sel_val = min([i for i in c if i != 0], key=abs)
    if abs(sel_val) != 1: # det must be changed
        print "Volume increased by %i" % abs(sel_val)
        assert 0, "abs(sel_val) = %s != 1" % abs(sel_val)
    idx = c.tolist().index(sel_val)
    #print idx, sel_val
    if idx != col:
        # change sign to keep the same det
        T[idx], T[col] = T[col].copy(), -T[idx]
        c[idx], c[col] = c[col], -c[idx]

    T[col] = dot(c,T)

    if c[col] < 0: # sign of det was changed, change it again 
        T[1] *= -1

    if double_T:
        T /= 2.

    return T


def is_integer(a, epsilon=1e-7):
    "return true if numpy Float array consists off all integers"
    return (numpy.abs(a - numpy.round(a)) < epsilon).all()

def find_smallest_multiplier(a, max_n=1000):
    """return the smallest positive integer n such that matrix a multiplied
       by n is an integer matrix
    """
    for i in range(1, max_n):
        if is_integer(i*a):
            return i
    raise ValueError("Sorry, we can't make this matrix integer:\n%s" % a)


@transpose_3x3
def make_csl_from_0_lattice(T, n):
    if n < 0:
        T[0] *= -1
        n *= -1
    while True:
        m = [find_smallest_multiplier(T[i]) for i in (0,1,2)]
        prod = m[0] * m[1] * m[2]
        #print "prod", prod, n
        if prod <= n:
            for i in range(3):
                T[i] *= m[i]
            if prod < n:
                assert n % prod == 0
                T[0] *= n / prod
            break
        else:
            changed = False
            for i in range(3):
                for j in range(3):
                    if changed or i == j or m[i] == 1 or m[j] == 1:
                        continue
                    if m[i] <= m[j]:
                        a, b = i, j
                    else:
                        a, b = j, i
                    for k in plus_minus_gen(m[b]):
                        if find_smallest_multiplier(T[a] + k * T[b]) < m[a]:
                            T[a] += k * T[b]
                            changed = True
                            break
            assert changed, "Problem when making CSL from 0-lattice"
    assert is_integer(T)
    return T.round().astype(int)


def find_csl_matrix(sigma, R):
    """\
    Find matrix that determines the coincidence site lattice 
    for cubic structures.
    Parameters:
        sigma: CSL sigma
        R: rotation matrix
        centering: "f" for f.c.c., "b" for b.c.c. and None for p.c.
    Return value:
        matrix, which column vectors are the unit vectors of the CSL.
    Based on H. Grimmer et al., Acta Cryst. (1974) A30, 197
    """

    S = _get_S()

    Rs = dot(dot(inv(S), inv(R)), S)
    #print "xxx",  inv(R)
    #print Rs
    found = False
    # searching for unimodular transformation that makes det(Tp) != 0
    for U in _get_unimodular_transformation():
        assert det(U) in (1, -1)
        Tp = identity(3) - dot(U, Rs)
        if abs(det(Tp)) > 1e-6:
            found = True
            print "Unimodular transformation used:\n%s" % U 
            break
    if not found:
        print "Error. Try another unimodular transformation U to calculate T'"
        sys.exit(1)

    Xp = numpy.round(inv(Tp), 12)
    print "0-lattice:\n%s" % Xp
    n = round(sigma / det(Xp), 7)
    # n is an integral number of 0-lattice units per CSL unit
    print "det(X')=",det(Xp), "  n=", n
    csl = make_csl_from_0_lattice(Xp, n)
    assert is_integer(csl)
    csl = csl.round().astype(int)
    return beautify_matrix(csl)
    

def plus_minus_gen(n):
    for i in xrange(1, n):
        yield i
        yield -i

def zero_plus_minus_gen(n):
    yield 0
    for i in plus_minus_gen(n):
        yield i


@transpose_3x3
def find_orthorhombic_pbc(M):
    """\
     we don't change the last axis (!!!)
     vectors: 
         z2 = z
         x2 = b x + d y + e z
         y2 = c y + f x + g z
     the new matrix is:
                         [[x2] [y2] [z2]] 
                         [[  ] [  ] [  ]]
                         [[  ] [  ] [  ]]
     we simply try to guess b,c,d,e,f,g 
    """
    ##M *= 2 # make it integer, will be /=2 at the end
    assert is_integer(M)
    M = M.round().astype(int)

    n = 9
    pbc = None
    max_sq = 0
    x, y, z = M
    #detM = det(M)

    # We will try adding a multiple of one column to another. 
    # The column that is to be added can be multiplied by fractional number,
    # if the result is still integral
    x_ = x / gcd_array(x)
    y_ = y / gcd_array(y)
    z_ = z / gcd_array(z)
    #print "gcd_array", z, gcd_array(z)
    Mx = array([x, y_, z_])
    My = array([x_, y, z_])
    #print "mx",Mx
    #print "my",My

    z2 = z
    for b in plus_minus_gen(n):
        for d in zero_plus_minus_gen(n):
            for e in zero_plus_minus_gen(n):
                x2 = dot([b,d,e], Mx)
                #print x2
                if inner(z2, x2) != 0:
                    continue
                for c in plus_minus_gen(n):
                    for f in zero_plus_minus_gen(n):
                        for g in zero_plus_minus_gen(n):
                            y2 = dot([f,c,g], My)
                            if inner(z2, y2) == 0 and inner(x2, y2) == 0:
                                max_sq_ = max(dot(x2,x2), dot(y2,y2), 
                                              dot(z2,z2))
                                #print "#", max_sq_,
                                if pbc is None or max_sq_ < max_sq:
                                    pbc = array([x2, y2, z2])
                                    max_sq = max_sq_
    if pbc is None:
        print "No orthorhombic PBC found."
        sys.exit()
    ##pbc /= 2.

    id = identity(3)
    if (pbc[1] == id[0]).all() or (pbc[0] == -id[1]).all():
        pbc[0], pbc[1] = pbc[1], -pbc[0]
    elif (pbc[1] == -id[0]).all() or (pbc[0] == id[1]).all():
        pbc[0], pbc[1] = pbc[1], -pbc[0]

    return pbc


def find_type(type, Cp):
    for i,j,k in (0,0,1), (0,1,0), (1,0,0), (0,1,1), (1,0,1), (1,1,0), (1,1,1):
        if ((i * Cp[0] + j * Cp[1] + k * Cp[2]) % 2 == type).all():
            return [i,j,k]
    raise ValueError("find_type: %s not found" % type)

# see the paper by Grimmer, 1.3.1-1.3.3
@transpose_3x3
def pc2fcc(Cp):
    t1 = find_type([0,1,1], Cp)
    t2 = find_type([1,0,1], Cp)
    pos1 = t1.index(1)
    pos2 = t2.index(1)
    if pos2 == pos1:
        try:
            pos2 = t2.index(1, pos1+1)
        except ValueError:
            pos1 = t1.index(1, pos1+1)
    Z = identity(3)
    Z[pos1] = array(t1) / 2.
    Z[pos2] = array(t2) / 2.
    #print_matrix("Z (in pc2fcc)", Z.transpose())
    return dot(Z, Cp)

def print_list(hkl, max_angle=45., limit=1000):
    data = []
    for i in range(limit):
        tt = get_theta_m_n_list(hkl, i, verbose=False)
        for t in tt:
            theta, m, n = t
            if degrees(theta) <= max_angle:
                tup = (i, degrees(theta), m, n)
                data.append(tup)
                print "sigma=%3i    theta=%5.2f     m=%3i    n=%3i" % tup

    data.sort(key= lambda x: x[1])
    print " ============= Sorted by theta ================ "
    for i in data:
        print "sigma=%3i    theta=%5.2f     m=%3i    n=%3i" % i


def print_details(hkl, sigma):
    t = find_theta(hkl, sigma)
    if t is None:
        print "Not found."
        return
    theta, m, n = t
    print "min. theta = %.3f  for m=%i, n=%i" % (degrees(theta), m, n)
    R = rodrigues(hkl, theta)
    print
    print "R * sigma =\n%s" % (R * sigma)
    C = find_csl_matrix(sigma, R)
    print "CSL primitive cell (det=%s):\n%s" % (det(C), C)
    # optional, for FCC
    C = pc2fcc(C)
    C = beautify_matrix(C)
    print_matrix("CSL cell for fcc:", C)

    Cp = make_parallel_to_axis(C, col=2, axis=hkl)
    if (Cp != C).any():
        print "after making z || %s:\n%s" % (hkl, Cp)
    pbc = find_orthorhombic_pbc(Cp)
    print_matrix("Minimal(?) orthorhombic PBC", pbc)


def main():
    argc = len(sys.argv)
    if argc != 2 and argc != 3:
        print usage_string
        return
    assert len(sys.argv[1]) == 3
    hkl = tuple([int(i) for i in sys.argv[1]])
    if argc == 2:
        print_list(hkl)
    else:
        sigma = int(sys.argv[2])
        print_details(hkl, sigma)



if __name__ == '__main__':
    main()


