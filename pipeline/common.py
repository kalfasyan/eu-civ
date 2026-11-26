"""Shared helpers for the EU pipeline: projection, hex grid, IO."""
import json, math, os
import numpy as np
from pyproj import Transformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = ROOT + '/raw'  # downloads (not in git)
OUT = ROOT + '/data'
INTERIM = ROOT + '/interim'
os.makedirs(OUT, exist_ok=True)
os.makedirs(INTERIM, exist_ok=True)

EU27 = ['AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'EL', 'ES', 'FI', 'FR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU',
        'LV', 'MT', 'NL', 'PL', 'PT', 'RO', 'SE', 'SI', 'SK']
COUNTRY_NAMES = {'AT': 'Austria', 'BE': 'Belgium', 'BG': 'Bulgaria', 'CY': 'Cyprus', 'CZ': 'Czechia', 'DE': 'Germany',
                 'DK': 'Denmark', 'EE': 'Estonia', 'EL': 'Greece', 'ES': 'Spain', 'FI': 'Finland', 'FR': 'France',
                 'HR': 'Croatia', 'HU': 'Hungary', 'IE': 'Ireland', 'IT': 'Italy', 'LT': 'Lithuania', 'LU': 'Luxembourg',
                 'LV': 'Latvia', 'MT': 'Malta', 'NL': 'Netherlands', 'PL': 'Poland', 'PT': 'Portugal', 'RO': 'Romania',
                 'SE': 'Sweden', 'SI': 'Slovenia', 'SK': 'Slovakia'}
CAPITALS = {'AT': 'AT001MC', 'BE': 'BE001MC'}  # filled from metro codes ending in MC
# Outermost regions and the North African enclaves are left off the map (like the original skipped AK/HI).
EXCLUDED_PREFIXES = ('FRY', 'ES70', 'PT20', 'PT30', 'ES63', 'ES64')

TO3035 = Transformer.from_crs('EPSG:4326', 'EPSG:3035', always_xy=True)
TO4326 = Transformer.from_crs('EPSG:3035', 'EPSG:4326', always_xy=True)

SQRT3 = math.sqrt(3)


def load_json(p):
    with open(p) as f:
        return json.load(f)


def save_json(name, obj, digits=None):
    p = os.path.join(OUT, name + '.json')
    with open(p, 'w') as f:
        json.dump(obj, f, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    print('wrote', p, os.path.getsize(p) // 1024, 'kB')


def save_interim(name, obj):
    with open(os.path.join(INTERIM, name + '.json'), 'w') as f:
        json.dump(obj, f, separators=(',', ':'))


def load_interim(name):
    return load_json(os.path.join(INTERIM, name + '.json'))


class Proj:
    """lon/lat -> map km (EPSG:3035 LAEA Europe, shifted so top-left is 0,0 and y is down)."""

    def __init__(self, min_x, max_y, margin):
        self.min_x, self.max_y, self.margin = min_x, max_y, margin

    def from3035(self, X, Y):
        X = np.asarray(X, float) / 1000.0
        Y = np.asarray(Y, float) / 1000.0
        return X - self.min_x + self.margin, self.max_y - Y + self.margin

    def to3035(self, x, y):
        return (np.asarray(x) + self.min_x - self.margin) * 1000.0, (self.max_y + self.margin - np.asarray(y)) * 1000.0

    def __call__(self, lon, lat):
        X, Y = TO3035.transform(lon, lat)
        return self.from3035(X, Y)

    def inverse(self, x, y):
        X, Y = self.to3035(x, y)
        return TO4326.transform(X, Y)

    def to_dict(self):
        return {'min_x': self.min_x, 'max_y': self.max_y, 'margin': self.margin, 'crs': 'EPSG:3035'}


class Grid:
    def __init__(self, radius, cols, rows):
        self.radius, self.cols, self.rows = radius, cols, rows
        self.size = cols * rows

    def center(self, i):
        i = np.asarray(i)
        col, row = i % self.cols, i // self.cols
        return SQRT3 * self.radius * (col + 0.5 * (row & 1)), 1.5 * self.radius * row

    def cell_at(self, x, y):
        x = np.asarray(x, float); y = np.asarray(y, float)
        q = (SQRT3 / 3 * x - y / 3) / self.radius
        r = (2 / 3 * y) / self.radius
        cx, cz = q, r
        cy = -cx - cz
        rx, ry, rz = np.floor(cx + 0.5), np.floor(cy + 0.5), np.floor(cz + 0.5)
        dx, dy, dz = np.abs(rx - cx), np.abs(ry - cy), np.abs(rz - cz)
        a = (dx > dy) & (dx > dz)
        b = (~a) & (dy <= dz)
        rx = np.where(a, -ry - rz, rx)
        rz = np.where(b, -rx - ry, rz)
        row = rz.astype(int)
        col = (rx + (row - (row & 1)) // 2).astype(int)
        ok = (col >= 0) & (col < self.cols) & (row >= 0) & (row < self.rows)
        return np.where(ok, row * self.cols + col, -1)

    NB = (((1, 0), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1)),
          ((1, 0), (1, 1), (0, 1), (-1, 0), (0, -1), (1, -1)))

    def neighbours(self, i):
        col, row = i % self.cols, i // self.cols
        out = []
        for dc, dr in self.NB[row & 1]:
            c, r = col + dc, row + dr
            if 0 <= c < self.cols and 0 <= r < self.rows:
                out.append(r * self.cols + c)
        return out

    def to_dict(self):
        return {'radius': self.radius, 'cols': self.cols, 'rows': self.rows}


def world_ctx():
    w = load_interim('_world_meta')
    p = Proj(**{k: w['projection'][k] for k in ('min_x', 'max_y', 'margin')})
    g = Grid(**w['grid'])
    return w, p, g
