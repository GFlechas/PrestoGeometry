"""Entry point: python -m presto_geometry"""

import click
from presto_geometry import __version__


@click.command()
@click.option("--input", "-i", "input_dir", required=True, type=click.Path(exists=True), help="Folder of building photos")
@click.option("--output", "-o", "output_dir", required=True, type=click.Path(), help="Destination folder for exported files")
@click.option("--format", "-f", "formats", multiple=True, default=["idf", "osm", "hpxml"], show_default=True, help="Export format(s)")
@click.version_option(__version__)
def main(input_dir, output_dir, formats):
    """Convert building photos to energy model geometry."""
    click.echo(f"PrestoGeometry v{__version__}")
    click.echo(f"Input:   {input_dir}")
    click.echo(f"Output:  {output_dir}")
    click.echo(f"Formats: {', '.join(formats)}")
    click.echo("(pipeline not yet implemented)")


if __name__ == "__main__":
    main()
