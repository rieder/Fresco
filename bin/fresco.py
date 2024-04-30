#!/usr/bin/env python
"""
Fresco creates a "simulated observation" of a set of particles.
Particles can be "stars" (point sources emitting light) or "gas" (emitting,
reflecting and/or obscuring light). Gas may also be displayed with contour
lines.
"""

import sys
import os
import argparse

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from amuse.units import units, nbody_system
from amuse.datamodel import Particles
from amuse.io import read_set_from_file
from amuse.datamodel.rotation import rotate

from amuse.plot.fresco.fieldstars import new_field_stars
from amuse.plot.fresco.fresco import (
    evolve_to_age,
    make_image,
    column_density_map,
    initialise_image,
)


def fresco_argument_parser(parser=None):
    "Parse command line arguments"
    if parser is None:
        parser = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
    parser.add_argument(
        "--filetype",
        dest="filetype",
        default="amuse",
        help="file type, valid are all types AMUSE can read",
    )
    parser.add_argument(
        "-s",
        dest="starsfilename",
        help="file containing stars (optional)",
    )
    parser.add_argument(
        "-g",
        dest="gasfilename",
        help="file containing gas (optional)",
    )
    parser.add_argument(
        "-f",
        dest="followfilename",
        help=("file containing star keys to center on (optional, implies --com)"),
    )
    parser.add_argument(
        "-o",
        dest="imagefilename",
        help="write image to this file",
    )
    parser.add_argument(
        "--imagetype",
        dest="imagetype",
        default="png",
        help="image file type",
    )
    parser.add_argument(
        "-b",
        dest="sourcebands",
        default="ubvri",
        help="colour bands to use",
    )
    parser.add_argument(
        "-a",
        dest="age",
        default=100 | units.Myr,
        type=units.Myr,
        help="age of the stars",
    )
    parser.add_argument(
        "-w",
        dest="width",
        default=5 | units.pc,
        type=units.pc,
        help="image width",
    )
    parser.add_argument(
        "-x",
        dest="plot_axes",
        action="store_true",
        default=False,
        help="plot axes",
    )
    parser.add_argument(
        "--ext",
        dest="calculate_extinction",
        action="store_true",
        default=False,
        help="include extinction by dust",
    )
    parser.add_argument(
        "--seed",
        dest="seed",
        default=1701,
        type=int,
        help="random seed",
    )
    parser.add_argument(
        "--vmax",
        dest="vmax",
        default=0,
        type=float,
        help="vmax value",
    )
    parser.add_argument(
        "--field",
        dest="n_fieldstars",
        default=0,
        type=int,
        help="add N field stars (optional)",
    )
    parser.add_argument(
        "--ax",
        dest="angle_x",
        default=0 | units.deg,
        type=units.deg,
        help="Rotation step around x-axis",
    )
    parser.add_argument(
        "--ay",
        dest="angle_y",
        default=0 | units.deg,
        type=units.deg,
        help="Rotation step around y-axis",
    )
    parser.add_argument(
        "--az",
        dest="angle_z",
        default=0 | units.deg,
        type=units.deg,
        help="Rotation step around z-axis",
    )
    parser.add_argument(
        "--frames",
        dest="frames",
        default=1,
        type=int,
        help="Number of frames (>1: rotate around x,y,z)",
    )
    parser.add_argument(
        "--px",
        dest="pixels",
        default=2048,
        type=int,
        help="Number of pixels along each axis",
    )
    parser.add_argument(
        "--psf",
        dest="psf_type",
        default="hubble",
        help=(
            "PSF type. Looks for a .fits file of the given name, uses this if "
            "it exists.\n"
            "Otherwise, 'hubble', 'wfc3', 'wfpc2', 'gaussian' and a local PSF file "
            "are valid options."
        ),
    )
    parser.add_argument(
        "--sigma",
        dest="psf_sigma",
        default=1.0,
        type=float,
        help="PSF sigma (only used if PSF type is gaussian)",
    )
    parser.add_argument(
        "--fl",
        dest="fixed_luminosity",
        action="store_true",
        default=False,
        help="Use a fixed, equal luminosity and temperature for all stars",
    )
    parser.add_argument(
        "--contours",
        dest="contours",
        action="store_true",
        default=False,
        help="Plot gas contour lines",
    )
    parser.add_argument(
        "--com",
        dest="use_com",
        action="store_true",
        default=False,
        help="Center on center of mass",
    )
    parser.add_argument(
        "--xo",
        dest="x_offset",
        default=0.0 | units.pc,
        type=units.pc,
        help="X offset",
    )
    parser.add_argument(
        "--yo",
        dest="y_offset",
        default=0.0 | units.pc,
        type=units.pc,
        help="Y offset",
    )
    parser.add_argument(
        "--zo",
        dest="z_offset",
        default=0.0 | units.pc,
        type=units.pc,
        help="Z offset",
    )
    return parser.parse_args()


def main():
    # Standard settings
    stellar_evolution = True
    se_code = "SeBa"
    length_unit = units.parsec
    dpi = 600
    percentile = 0.9995  # for determining vmax

    # Parse arguments
    args = fresco_argument_parser()
    if args.fixed_luminosity:
        stellar_evolution = False
    starsfilename = args.starsfilename
    gasfilename = args.gasfilename
    followfilename = args.followfilename
    imagefilename = args.imagefilename
    imagetype = args.imagetype
    vmax = args.vmax if args.vmax > 0 else None
    n_fieldstars = args.n_fieldstars
    filetype = args.filetype
    contours = args.contours
    np.random.seed(args.seed)
    plot_axes = args.plot_axes
    angle_x = args.angle_x
    angle_y = args.angle_y
    angle_z = args.angle_z
    sourcebands = args.sourcebands
    psf_type = args.psf_type
    if os.path.exists(psf_type):
        psf_file = psf_type
        psf_type = "file"
    else:
        psf_file = None
        psf_type = psf_type.lower()
        if psf_type not in ["hubble", "gaussian"]:
            print(f"Invalid PSF type or file does not exist: {psf_type}")
            sys.exit()
    psf_sigma = args.psf_sigma
    age = args.age
    image_width = args.width
    pixels = args.pixels
    frames = args.frames
    if followfilename is not None:
        use_com = True
    else:
        use_com = args.use_com
    x_offset = args.x_offset
    y_offset = args.y_offset
    z_offset = args.z_offset
    extinction = args.calculate_extinction

    # sanity check
    if starsfilename is None:
        nostars = True
    elif not os.path.exists(starsfilename):
        nostars = True
    else:
        nostars = False
    if gasfilename is None:
        nogas = True
    elif not os.path.exists(gasfilename):
        nogas = True
    else:
        nogas = False
    if nostars and nogas:
        raise FileNotFoundError("Need at least one of a stars or gas file")

    # Derived settings

    image_size = [pixels, pixels]
    # If the nr of pixels is changed, zoom the PSF accordingly.
    zoom_factor = pixels / 2048.0

    if starsfilename:
        stars = read_set_from_file(
            starsfilename,
            filetype,
            close_file=True,
        )
        if stellar_evolution and (age > 0 | units.Myr):
            print(("Calculating luminosity/temperature for %s old stars..." % (age)))
            evolve_to_age(stars, age, stellar_evolution=se_code)
        elif args.fixed_luminosity:
            for band in sourcebands:
                setattr(stars, band + "_band", 1.0 | units.LSun)
        if use_com:
            if followfilename is not None:
                followstars = read_set_from_file(
                    followfilename,
                    filetype,
                    close_file=True,
                )
                center_on_these_stars = followstars.get_intersecting_subset_in(
                    stars,
                )
            else:
                center_on_these_stars = stars
            com = center_on_these_stars.center_of_mass()
            x_offset, y_offset, z_offset = com

        # Select only the relevant gas particles (plus a margin)
        # note: the margin should at least be half the PSF width - probably
        # more
        if image_width == "max" | units.pc:
            minx = stars.x.min()
            maxx = stars.x.max()
            miny = stars.y.min()
            maxy = stars.y.max()
            image_width = max(maxx - minx, maxy - miny)
            x_offset = (maxx + minx) / 2
            y_offset = (maxy + miny) / 2
        stars.x -= x_offset
        stars.y -= y_offset
        stars.z -= z_offset
        minx = 1.5 * -image_width / 2
        maxx = 1.5 * image_width / 2
        miny = 1.5 * -image_width / 2
        maxy = 1.5 * image_width / 2
        stars = stars[stars.x > minx]
        stars = stars[stars.x < maxx]
        stars = stars[stars.y > miny]
        stars = stars[stars.y < maxy]
    else:
        stars = Particles()

    if n_fieldstars:
        minage = 400 | units.Myr
        maxage = 12 | units.Gyr
        fieldstars = new_field_stars(
            n_fieldstars,
            width=image_width,
            height=image_width,
        )
        fieldstars.age = minage + (np.random.sample(n_fieldstars) * (maxage - minage))
        evolve_to_age(fieldstars, 0 | units.yr, stellar_evolution=se_code)
        stars.add_particles(fieldstars)

    if gasfilename:
        gas = read_set_from_file(
            gasfilename,
            filetype,
            close_file=True,
        )
        if use_com:
            if stars.is_empty():
                com = gas.center_of_mass()
                x_offset, y_offset, z_offset = com
        gas.x -= x_offset
        gas.y -= y_offset
        gas.z -= z_offset
        # Gadget and Fi disagree on the definition of h_smooth.
        # For gadget, need to divide by 2 to get the Fi value (??)
        # gas.h_smooth *= 0.5
        # gas.radius = gas.h_smooth

        # Select only the relevant gas particles (plus a margin)
        minx = 1.1 * -image_width / 2
        maxx = 1.1 * image_width / 2
        miny = 1.1 * -image_width / 2
        maxy = 1.1 * image_width / 2
        gas_ = gas.select(
            lambda x, y: x > minx and x < maxx and y > miny and y < maxy, ["x", "y"]
        )
        gas = gas_
    else:
        gas = Particles()
    # gas.h_smooth = 0.05 | units.parsec

    converter = nbody_system.nbody_to_si(
        stars.total_mass() if not stars.is_empty() else gas.total_mass(),
        image_width,
    )

    # Initialise figure and axes
    fig = initialise_image(
        dpi=dpi,
        image_size=image_size,
        length_unit=length_unit,
        image_width=image_width,
        plot_axes=plot_axes,
        x_offset=x_offset,
        y_offset=y_offset,
        z_offset=z_offset,
    )
    ax = fig.get_axes()[0]
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()

    if not stars.is_empty():
        rotate(
            stars,
            (frames - 1) * angle_x,
            (frames - 1) * angle_y,
            (frames - 1) * angle_z,
        )
    if not gas.is_empty():
        rotate(
            gas, (frames - 1) * angle_x, (frames - 1) * angle_y, (frames - 1) * angle_z
        )
    for frame in range(frames):
        frame += frames
        print(
            f"frame {frame}, "
            f"angle: {frame * angle_x.value_in(units.deg)} "
            f"{frame * angle_y.value_in(units.deg)} "
            f"{frame * angle_z.value_in(units.deg)}"
        )
        fig = initialise_image(fig)

        if (frame != 0) or (frames == 1):
            if not stars.is_empty():
                rotate(stars, angle_x, angle_y, angle_z)
            if not gas.is_empty():
                rotate(gas, angle_x, angle_y, angle_z)

        image, vmax = make_image(
            stars=stars if not stars.is_empty() else None,
            gas=gas if not gas.is_empty() else None,
            converter=converter,
            image_width=image_width,
            image_size=image_size,
            percentile=percentile,
            calc_temperature=False if not hasattr(stars, "temperature") else True,
            age=age,
            vmax=vmax,
            sourcebands=sourcebands,
            zoom_factor=zoom_factor,
            psf_type=psf_type,
            psf_file=psf_file,
            psf_sigma=psf_sigma,
            return_vmax=True,
            extinction=extinction,
        )
        print(f"vmax = {vmax}")

        if not stars.is_empty():
            ax.imshow(
                image,
                origin="lower",
                extent=[
                    xmin,
                    xmax,
                    ymin,
                    ymax,
                ],
            )
            if contours and not gas.is_empty():
                gascontours = column_density_map(
                    gas,
                    zoom_factor=zoom_factor,
                    image_width=image_width,
                    image_size=image_size,
                )
                gascontours[np.isnan(gascontours)] = 0.0
                vmax = np.max(gascontours) / 2
                # vmin = np.min(image[np.where(image > 0.0)])
                vmin = vmax / 100
                levels = (
                    10
                    ** (
                        np.linspace(
                            np.log10(vmin),
                            np.log10(vmax),
                            num=5,
                        )
                    )[1:]
                )
                # print(vmin, vmax)
                # print(levels)
                ax.contour(
                    origin="lower",
                    levels=levels,
                    colors="white",
                    linewidths=0.1,
                    extent=[
                        xmin,
                        xmax,
                        ymin,
                        ymax,
                    ],
                )
        else:
            image = column_density_map(
                gas,
                image_width=image_width,
                image_size=image_size,
            )

            ax.imshow(
                image,
                origin="lower",
                extent=[
                    xmin,
                    xmax,
                    ymin,
                    ymax,
                ],
                cmap="gray",
            )

        if frames > 1:
            savefilename = "%s-%06i.%s" % (
                imagefilename if imagefilename is not None else "test",
                frame,
                imagetype,
            )
        else:
            savefilename = "%s.%s" % (
                imagefilename if imagefilename is not None else "test",
                imagetype,
            )
        plt.savefig(
            savefilename,
            dpi=dpi,
        )


if __name__ == "__main__":
    main()
    print(
        "------------------\n"
        "\n"
        "Fresco is built on the tools below."
        " If you use Fresco for your publication, please cite the following"
        " references:\n"
        "\n"
        "Fresco:"
        " Steven Rieder & Inti Pelupessy."
        " rieder/Fresco (2019)."
        " doi:10.5281/zenodo.3362342\n"
        "AMUSE:"
        " Simon Portegies Zwart & Steve McMillan."
        " Astrophysical Recipes; The art of AMUSE (2019)."
        " ADS bibcode: 2018araa.book.....P."
        " doi:10.1088/978-0-7503-1320-9\n"
        "Matplotlib:"
        " John D. Hunter."
        " Matplotlib: A 2D Graphics Environment."
        " doi:10.1109/MCSE.2007.55\n"
        "Numpy:"
        " Stéfan van der Walt, S. Chris Colbert and Gaël Varoquaux."
        " The NumPy Array: A Structure for Efficient Numerical Computation."
        " doi:10.1109/MCSE.2011.37\n"
        "Python:"
        " Guido van Rossum."
        " Extending and Embedding the Python Interpreter."
        " May 1995. CWI Report CS-R9527.\n"
    )
