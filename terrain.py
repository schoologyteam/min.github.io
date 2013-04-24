"""
Terrain generating algorithm
"""

# Imports, sorted alphabetically.

# Python packages
from math import sqrt, floor
import random

# Third-party packages
from debug import performance_info
from perlin import SimplexNoise

# Modules from this project
from blocks import *
from utils import FastRandom, fast_abs
from nature import *
from world import *
import globals as G



# Improved Perlin Noise based on Improved Noise reference implementation by Ken Perlin
class PerlinNoise(object):
    def __init__(self, seed):
        rand = FastRandom(seed)

        self.perm = [ None ] * 512
        noise_tbl = [ None ] * 256

        self.PERSISTENCE = 2.1379201
        self.H = 0.836281
        self.OCTAVES = 9
        self.weights = [ None ] * self.OCTAVES
        self.regen_weight = True

        for i in range(0, 256):
            noise_tbl[i] = i

        for i in range(0, 256):
            j = rand.randint() % 256
            j = fast_abs(j)

            noise_tbl[i], noise_tbl[j] = noise_tbl[j], noise_tbl[i]

        for i in range(0, 256):
            self.perm[i] = self.perm[i + 256] = noise_tbl[i]

    def fade(self, t) :
        return t * t * t * (t * (t * 6 - 15) + 10)

    # linear interpolate
    def lerp(self, t, a, b):
        return a + t * (b - a)

    def grad(self, hash, x, y, z):
        h = hash & 15
        u = x if h < 8 else y
        if h < 4:
            v = y
        elif h == 12 or h ==14:
            v = x
        else:
            v = z
        return (u if (h & 1) == 0 else - u) + (v if (h & 2) == 0 else -v)

    def noise(self, x, y, z):
        X = int(floor(x)) & 255
        Y = int(floor(y)) & 255
        Z = int(floor(z)) & 255

        x -= floor(x)
        y -= floor(y)
        z -= floor(z)

        u = self.fade(x)
        v = self.fade(y)
        w = self.fade(z)

        A = self.perm[X] + Y
        AA = self.perm[A] + Z
        AB = self.perm[(A + 1)] + Z
        B = self.perm[(X + 1)] + Y
        BA = self.perm[B] + Z
        BB = self.perm[(B + 1)] + Z

        return self.lerp(w, self.lerp(v, self.lerp(u, self.grad(self.perm[AA], x, y, z),
                                self.grad(self.perm[BA], x - 1, y, z)),
                            self.lerp(u, self.grad(self.perm[AB], x, y - 1, z),
                                self.grad(self.perm[BB], x - 1, y - 1, z))),
                            self.lerp(v, self.lerp(u, self.grad(self.perm[(AA + 1)], x, y, z - 1),
                                self.grad(self.perm[(BA + 1)], x - 1, y, z - 1)),
                            self.lerp(u, self.grad(self.perm[(AB + 1)], x, y - 1, z - 1),
                                self.grad(self.perm[(BB + 1)], x - 1, y - 1, z - 1))))

    def fBm(self, x, y, z):
        total = 0.0

        if self.regen_weight:
            self.weights = [ None ] * self.OCTAVES
            for n in range(0, self.OCTAVES):
                self.weights[n] = self.PERSISTENCE ** (-self.H * n)

            regen_weight = False

        for n in range(0, self.OCTAVES):
            total += self.noise(x, y, z) * self.weights[n]

            x *= self.PERSISTENCE
            y *= self.PERSISTENCE
            z *= self.PERSISTENCE

        return total

    @property
    def octave(self):
        return self.OCTAVES

    @octave.setter
    def octave(self, value):
        self.OCTAVES = value
        self.regen_weight = True

CHUNK_X_SIZE = 16
CHUNK_Z_SIZE = 16
CHUNK_Y_SIZE = 256

# create a array with size x_size*y_size*z_size
def init_3d_list(x_size, y_size, z_size):
    # initialize block list
    xblks = {}
    for x in xrange(x_size):
        yblks = {}
        for y in xrange(y_size):
            zblks = {}
            for z in xrange(z_size):
                zblks[z] = None
            yblks[y] = zblks
        xblks[x] = yblks
    return xblks

class Chunk(object):
    def __init__(self, position, x_size=CHUNK_X_SIZE, y_size=CHUNK_Y_SIZE, z_size=CHUNK_Z_SIZE):
        self.x_pos, self.y_pos, self.z_pos = position
        self.x_size = x_size
        self.y_size = y_size
        self.z_size = z_size
        self.blocks = init_3d_list(x_size, y_size, z_size)

    def get_block(self, x, y, z):
        return self.blocks[x][y][z]

    def set_block(self, x, y, z, block):
        self.blocks[x][y][z] = block

    def world_block_xpos(self, x):
        return self.x_pos + x

    def world_block_ypos(self, y):
        return self.y_pos + y

    def world_block_zpos(self, z):
        return self.z_pos + z

SAMPLE_RATE_HOR = 4
SAMPLE_RATE_VER = 4

class BiomeGenerator(object):
    def __init__(self, seed):
        self.temperature_gen = PerlinNoise(seed + 97)
        self.humidity_gen = PerlinNoise(seed + 147)

    def _clamp(self, a):
        if a > 1:
            return 1
        elif a < 0:
            return 0
        else:
            return a

    def get_humidity(self, x, z):
        return float(self._clamp((self.humidity_gen.fBm(x * 0.0005, 0, 0.0005 * z) + 1.0) / 2.0))

    def get_temperature(self,x, z):
        return float(self._clamp((self.temperature_gen.fBm(x * 0.0005, 0, 0.0005 * z) + 1.0) / 2.0))

    def get_biome_type(self, x, z):
        x = int(x)
        z = int(z)
        temp = self.get_temperature(x, z)
        humidity = self.get_humidity(x, z) * temp

        if temp >= 0.5 and humidity < 0.3:
            return G.DESERT
        elif 0.3 <= humidity <= 0.6 and temp >= 0.5:
            return G.PLAINS
        elif temp <= 0.3 and humidity > 0.5:
            return G.SNOW
        elif 0.2 <= humidity <= 0.6 and temp < 0.5:
            return G.MOUNTAINS

        return G.FOREST

class TerrainGeneratorBase(object):
    def __init__(self, seed):
        self.seed = seed

    def generate_chunk(self, chunk_x, chunk_y, chunk_z):
        pass

    def generate_sector(self, sector):
        pass

class TerrainGenerator(TerrainGeneratorBase):
    def __init__(self, seed):
        super(TerrainGenerator, self).__init__(seed)
        self.base_gen = PerlinNoise(seed)
        self.base_gen.octave = 8
        self.ocean_gen = PerlinNoise(seed + 11)
        self.ocean_gen.octave = 8
        self.river_gen = PerlinNoise(seed + 31)
        self.river_gen.octave = 8
        self.mount_gen = PerlinNoise(seed + 41)
        self.hill_gen = PerlinNoise(seed + 71)
        self.cave_gen = PerlinNoise(seed + 141)
        self.biome_gen = BiomeGenerator(seed) 

    def set_seed(self, seed):
        self.base_gen = PerlinNoise(seed)
        self.base_gen.octave = 8
        self.ocean_gen = PerlinNoise(seed + 11)
        self.ocean_gen.octave = 8
        self.river_gen = PerlinNoise(seed + 31)
        self.river_gen.octave = 8
        self.mount_gen = PerlinNoise(seed + 41)
        self.hill_gen = PerlinNoise(seed + 71)
        self.cave_gen = PerlinNoise(seed + 141)
        self.biome_gen = BiomeGenerator(seed) 
        self.seed = seed

    def generate_chunk(self, chunk_x, chunk_y, chunk_z):
        c = Chunk(position=(chunk_x, chunk_y, chunk_z))

        # density map
        d_map = init_3d_list(c.x_size + 1, c.y_size + 1, c.z_size + 1)

        for x in range(0, c.x_size + SAMPLE_RATE_HOR, SAMPLE_RATE_HOR):
            for z in range(0, c.z_size + SAMPLE_RATE_HOR, SAMPLE_RATE_HOR):
                for y in range(0, c.y_size + SAMPLE_RATE_VER, SAMPLE_RATE_VER):
                    d_map[x][y][z] = self.density(c.world_block_xpos(x), y, c.world_block_zpos(z))
                    #print d_map[x][y][z]

        # interpolate the missing values
        self.tri_lerp_d_map(d_map)

        for x in range(0, CHUNK_X_SIZE):
            for z in range(0, CHUNK_Z_SIZE):
                biome_type = self.biome_gen.get_biome_type(x, z)
                first_block = -1
                for y in range(CHUNK_Y_SIZE - 1, 0, -1):
                    if y == 0:
                        c.set_block(x, y, z, bed_block)
                        break

                    # 32: sea level
                    if 0 < y <= 32:
                        c.set_block(x, y, z, water_block)

                    den = d_map[x][y][z]

                    if 0 <= den < 32:
                        if first_block == -1:
                            first_block = y

                        if self.cave_density(c.world_block_xpos(x), y, c.world_block_zpos(z)) > -0.7:
                            c = self.gen_outer_layer(x, y, z, first_block, c, biome_type)
                        else:
                            c.set_block(x, y, z, air_block)

                        continue
                    elif den >= 32:

                        if first_block == -1:
                            first_block = y

                        if self.cave_density(c.world_block_xpos(x), y, c.world_block_zpos(z)) > -0.6:
                            c = self.gen_inner_layer(x, y, z, c)
                        else:
                            c.set_block(x, y, z, air_block)

                        continue

                    first_block = -1
        return c

    def gen_inner_layer(self, x, y, z, c):
        # Mineral generation should be here also
        c.set_block(x, y, z, stone_block)
        return c

    def gen_outer_layer(self, x, y, z, first_block, c, biome_type):

        depth = int(first_block - y)


        if biome_type == G.PLAINS or biome_type == G.MOUNTAINS or biome_type == G.FOREST:
            if 28 <= y <= 34:
                c.set_block(x, y, z, sand_block)
            elif depth == 0 and 32 < y < 128:
                c.set_block(x, y, z, grass_block)
            elif depth > 32: 
                c.set_block(x, y, z, stone_block)
            else:
                c.set_block(x, y, z, dirt_block)
        elif biome_type == G.SNOW:
            if depth == 0 and y >= 32:
                    c.set_block(x, y, z, snow_block)
            elif depth > 32:
                c.set_block(x, y, z, stone_block)
            else:
                c.set_block(x, y, z, dirt_block)
        elif biome_type == G.DESERT:
            if depth > 8: 
                c.set_block(x, y, z, stone_block)
            else:
                c.set_block(x, y, z, sand_block)

        return c

    def lerp(self, x, x1, x2, v00, v01):
        return (float(x2 - x) / float(x2 - x1)) * v00 + (float(x - x1) / float(x2 - x1)) * v01

    def tri_lerp(self,x, y, z, v000, v001, v010, v011, v100, v101, v110, v111, x1, x2, y1, y2, z1, z2):
        x00 = self.lerp(x, x1, x2, v000, v100)
        x10 = self.lerp(x, x1, x2, v010, v110)
        x01 = self.lerp(x, x1, x2, v001, v101)
        x11 = self.lerp(x, x1, x2, v011, v111)
        u = self.lerp(y, y1, y2, x00, x01)
        v = self.lerp(y, y1, y2, x10, x11)
        return self.lerp(z, z1, z2, u, v)

    def tri_lerp_d_map(self, d_map):
        for x in range(0, CHUNK_X_SIZE):
            for y in range(0, CHUNK_Y_SIZE):
                for z in range(0, CHUNK_Z_SIZE):
                    if not (x % SAMPLE_RATE_HOR == 0 and y % SAMPLE_RATE_VER == 0 and z % SAMPLE_RATE_HOR == 0):
                        offsetX = int((x / SAMPLE_RATE_HOR) * SAMPLE_RATE_HOR)
                        offsetY = int((y / SAMPLE_RATE_VER) * SAMPLE_RATE_VER)
                        offsetZ = int((z / SAMPLE_RATE_HOR) * SAMPLE_RATE_HOR)
                        d_map[x][y][z] = self.tri_lerp(x, y, z, d_map[offsetX][offsetY][offsetZ], d_map[offsetX][SAMPLE_RATE_VER + offsetY][offsetZ], d_map[offsetX][offsetY][offsetZ + SAMPLE_RATE_HOR],
                                                                d_map[offsetX][offsetY + SAMPLE_RATE_VER][offsetZ + SAMPLE_RATE_HOR], d_map[SAMPLE_RATE_HOR + offsetX][offsetY][offsetZ], d_map[SAMPLE_RATE_HOR + offsetX][offsetY + SAMPLE_RATE_VER][offsetZ],
                                                                d_map[SAMPLE_RATE_HOR + offsetX][offsetY][offsetZ + SAMPLE_RATE_HOR], d_map[SAMPLE_RATE_HOR + offsetX][offsetY + SAMPLE_RATE_VER][offsetZ + SAMPLE_RATE_HOR], offsetX, SAMPLE_RATE_HOR + offsetX, offsetY,
                                                                SAMPLE_RATE_VER + offsetY, offsetZ, offsetZ + SAMPLE_RATE_HOR)

    def _clamp(self, a):
        if a > 1:
            return 1
        elif a < 0:
            return 0
        else:
            return a

    def density(self, x, y, z):
        height = self.base_terrain(x, z)
        ocean = self.ocean_terrain(x, z)
        river = self.rive_terrain(x, z)

        mountains = self.mount_density(x, y, z)
        hills = self.hill_density(x, y, z)

        flatten = self._clamp(((CHUNK_Y_SIZE - 16) - y) / int(CHUNK_Y_SIZE * 0.10))

        return -y + (((32.0 + height * 32.0) * self._clamp(river + 0.25) * self._clamp(ocean + 0.25)) + mountains * 1024.0 + hills * 128.0) * flatten

    def base_terrain(self, x, z):
        return self._clamp((self.base_gen.fBm(0.004 * x, 0, 0.004 * z) + 1.0) / 2.0)

    def ocean_terrain(self, x, z):
        return self._clamp(self.ocean_gen.fBm(0.0009 * x, 0, 0.0009 * z) * 8.0)

    def rive_terrain(self, x, z):
        return self._clamp((sqrt(fast_abs(self.river_gen.fBm(0.0008 * x, 0, 0.0008 * z))) - 0.1) * 7.0)

    def mount_density(self, x, y, z):
        ret = self.mount_gen.fBm(x * 0.002, y * 0.001, z * 0.002)
        return ret if ret > 0 else 0

    def hill_density(self, x, y, z):
        ret = self.hill_gen.fBm(x * 0.008, y * 0.006, z * 0.008) - 0.1
        return ret if ret > 0 else 0

    def cave_density(self, x, y, z):
        return self.cave_gen.fBm(x * 0.02, y * 0.02, z * 0.02)

class TerrainGeneratorSimple(TerrainGeneratorBase):
    """
    A simple and fast use of (Simplex) Perlin Noise to generate a heightmap
    Based on Jimx's work on the above TerrainGenerator class
    See http://code.google.com/p/fractalterraingeneration/wiki/Fractional_Brownian_Motion for more info
    """
    def __init__(self, world, seed):
        super(TerrainGeneratorSimple, self).__init__(seed)
        self.world = world
        self.seed = seed
        self.rand = random.Random(seed)
        perm = range(255)
        self.rand.shuffle(perm)
        self.noise = SimplexNoise(permutation_table=perm).noise2
        #self.noise = PerlinNoise(seed).noise
        self.PERSISTENCE = 2.1379201 #AKA lacunarity
        self.H = 0.836281

        #Fun things to adjust
        self.OCTAVES = 9        #Higher linearly increases calc time; increases apparent 'randomness'
        self.height_range = 32  #If you raise this, you should shrink zoom_level equally
        self.height_base = 32   #The lowest point the perlin terrain will generate (below is "underground")
        self.island_shore = 38  #below this is sand, above is grass .. island only
        self.water_level = 36 # have water 2 block higher than base, allowing for some rivers...
        self.zoom_level = 0.002 #Smaller will create gentler, softer transitions. Larger is more mountainy
        #self.negative_biome_trigger = G.BIOME_BLOCK_TRIGGER - G.BIOME_BLOCK_TRIGGER - G.BIOME_BLOCK_TRIGGER  #  negative version of the biome trigger
        #print(self.negative_biome_trigger)
        self.negative_biome_trigger = -215


        # ores avaliable on the lowest level, closet to bedrock
        self.lowlevel_ores = ((stone_block,) * 75 + (diamondore_block,) * 2 + (sapphireore_block,) * 2)
        #  ores in the 'mid-level' .. also, the common ore blocks
        self.midlevel_ores = ((stone_block,) * 80 + (rubyore_block,) * 2 +
                         (coalore_block,) * 4 + (gravel_block,) * 5 +
                         (ironore_block,) * 5 + (lapisore_block,) * 2)
        # ores closest to the top level dirt and ground
        self.highlevel_ores = ((stone_block,) * 85 + (gravel_block,) * 5 + (coalore_block,) * 3 + (quartz_block,) * 5)
        self.underwater_blocks = ((sand_block,) * 70 + (gravel_block,) * 20 + ( clay_block,) * 10)
        #self.world_type_trees = (OakTree, BirchTree, WaterMelon, Pumpkin, YFlowers, Potato, Carrot, Rose)
        self.world_type_trees = (OakTree, BirchTree, JungleTree)
        self.world_type_plants = (Pumpkin, Potato, Carrot, WaterMelon)
        self.world_type_grass = (YFlowers, Fern, Rose, WildGrass0, WildGrass1, Cactus, WildGrass2, TallCactus, WildGrass3, WildGrass4, WildGrass5, WildGrass6, WildGrass7, DesertGrass)
        self.island_type_grass = (YFlowers, Rose, Fern)
        #This is a list of blocks that may leak over from adjacent sectors and whose presence doesn't mean the sector is generated
        self.autogenerated_blocks = VEGETATION_BLOCKS

        self.weights = [self.PERSISTENCE ** (-self.H * n) for n in xrange(self.OCTAVES)]
    def _clamp(self, a):
        if a > 1:
            return 0.9999 #So int rounds down properly and keeps it within the right sector
        elif a < 0:
            return 0
        else:
            return a
    def get_height(self,x,z):
        """ Given block coordinates, returns a block coordinate height """
        x *= self.zoom_level
        z *= self.zoom_level
        y = 0
        for weight in self.weights:
            y += self.noise(x, z) * weight

            x *= self.PERSISTENCE
            z *= self.PERSISTENCE

        return int(self.height_base + self._clamp((y+1.0)/2.0)*self.height_range)

    def generate_sector(self, sector):
        main_block = grass_block
        if G.BIOME_BLOCK_COUNT >= G.BIOME_BLOCK_TRIGGER or G.BIOME_BLOCK_COUNT <= G.BIOME_NEGATIVE_BLOCK_TRIGGER: #  or self.negative_biome_trigger:  # 215 or -215
            G.BIOME_BLOCK_COUNT = 0
            new_biomes = ('plains', 'desert', 'mountains', 'snow')
            print ('old biome was ' + G.TERRAIN_CHOICE)
            G.TERRAIN_CHOICE = self.rand.choice(new_biomes)
            print ('new biome is ' + G.TERRAIN_CHOICE)

        if G.TERRAIN_CHOICE == "plains":
            main_block = grass_block
            self.height_range = 32
            self.height_base = 32
            self.island_shore = 0
            self.water_level = 0
            self.zoom_level = 0.002
        elif G.TERRAIN_CHOICE == "snow":
            main_block = snowgrass_block
            self.height_range = 32
            self.height_base = 32
            self.island_shore = 34
            self.water_level = 33
            self.zoom_level = 0.002
        elif G.TERRAIN_CHOICE == "desert":
            main_block = sand_block
            self.height_range = 32
            self.height_base = 32
            self.island_shore = 32
            self.water_level = 0
            self.zoom_level = 0.002
        elif G.TERRAIN_CHOICE == "island":
            # Some grass that cant be on sand, for a clean beach
            self.world_type_grass = (YFlowers, Rose, Fern)
            main_block = grass_block
            self.height_range = 32
            self.height_base = 32
            self.island_shore = 38
            self.water_level = 36
            self.zoom_level = 0.002
        elif G.TERRAIN_CHOICE == "mountains":
            main_block = stone_block
            self.height_range = 32
            self.height_base = 32
            self.island_shore = 18
            self.water_level = 20
            self.zoom_level = 0.001

        world = self.world
        if sector in world.sectors:
            for pos in world.sectors[sector]:
                if world[pos] not in self.autogenerated_blocks:
                    return

        world.sectors[sector] = []  # Precache it incase it ends up being solid air, so it doesn't get regenerated indefinitely
        bx, by, bz = world.savingsystem.sector_to_blockpos(sector)

        if 0 <= by < (self.height_base + self.height_range):
            self.rand.seed(self.seed + "(%d,%d,%d)" % (bx, by, bz))

            bytop = by + 8

            # We pass these as local variables for performance and readability.
            # Functions:
            init_block = world.init_block
            generate_vegetation = world.generate_vegetation
            get_height = self.get_height
            choose = self.rand.choice
            rand_random = self.rand.random
            # Variables (that are static during what follows)
            TERRAIN_CHOICE = G.TERRAIN_CHOICE
            TREE_CHANCE = G.TREE_CHANCE
            WILDFOOD_CHANCE = G.WILDFOOD_CHANCE
            GRASS_CHANCE = G.GRASS_CHANCE
            height_base = self.height_base
            island_shore = self.island_shore
            water_level = self.water_level
            underwater_blocks = self.underwater_blocks
            world_type_trees = self.world_type_trees
            world_type_plants = self.world_type_plants
            world_type_grass = self.world_type_grass
            highlevel_ores = self.highlevel_ores
            midlevel_ores = self.midlevel_ores
            lowlevel_ores = self.lowlevel_ores

           # if TERRAIN_CHOICE == 'desert':
           #     world_type_grass = self.desert_type_grass

            for x in xrange(bx, bx + 8):
                for z in xrange(bz, bz + 8):
                    if by < height_base:
                        # For sectors outside of the height_range, no point checking the heightmap
                        y = height_base
                    else:
                        # The heightmap falls within our sector, generate surface stuff
                        y = get_height(x, z)
                        if y > bytop:
                            y = bytop

                        if TERRAIN_CHOICE == "mountains":
                            if 0 <= y <= 35:  # bottom level = grass
                                main_block = grass_block
                            if 36 <= y <= 54:  # mid level = rock
                                main_block = stone_block
                            if y >= 55:  # top level = snow
                                main_block = snow_block

                        if y <= water_level:
                            if TERRAIN_CHOICE != "desert":  # was y == self.height_base -- you can have water!
                                if TERRAIN_CHOICE == "snow":  # top block is ice
                                    init_block((x, water_level, z), ice_block)
                                else:
                                    init_block((x, water_level, z), water_block)
                                # init_block((x, y -1, z), water_block)
                                init_block((x, water_level - 2, z), choose(underwater_blocks))
                                init_block((x, water_level - 3, z), dirt_block)
                            if TERRAIN_CHOICE == "desert":  # no water for you!
                                init_block((x, y + 1, z), sand_block)
                                init_block((x, y, z), sand_block)
                                init_block((x, y - 1, z), sand_block)
                                init_block((x, y - 2, z), sandstone_block)
                                init_block((x, y - 3, z), sandstone_block)
                            y -= 3
                        elif y < bytop:
                            if TERRAIN_CHOICE == "island":  # always sand by the water, grass above
                                if y > island_shore:
                                    main_block = grass_block
                                else:
                                    main_block = sand_block
                            init_block((x, y, z), main_block)

                            veget_choice = rand_random()
                            veget_blocks = None
                            if veget_choice < TREE_CHANCE:
                                veget_blocks = world_type_trees
                            elif veget_choice < WILDFOOD_CHANCE:
                                veget_blocks = world_type_plants
                            elif veget_choice < GRASS_CHANCE:
                                veget_blocks = world_type_grass
                            if veget_blocks is not None:
                                generate_vegetation((x, y + 1, z),
                                                    choose(veget_blocks))

                            if main_block == sand_block:
                                underground_blocks = (
                                    sand_block, sand_block, sandstone_block)
                            elif main_block == stone_block:
                                underground_blocks = (stone_block,) * 3
                            else:
                                underground_blocks = (dirt_block,) * 3

                            for d, block in enumerate(underground_blocks,
                                                      start=1):
                                init_block((x, y - d, z), block)

                            y -= 3

                    for yy in xrange(by, y):
                        # ores and filler...
                        if yy >= 32:
                            blockset = highlevel_ores
                        elif yy > 8:
                            blockset = midlevel_ores
                        else:
                            blockset = lowlevel_ores
                        init_block((x, yy, z), choose(blockset))
                    if by == 0:
                        init_block((x, 0, z), bed_block)
