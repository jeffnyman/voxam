namespace Voxam.Core.Tests;

/// <summary>The §16 bitmaps as a pixel glass reads them.</summary>
public class Font3Tests
{
    // Every code from 32 to 126 has eight rows; nothing outside does,
    // and a stand-in string longer than one character is no code.
    [Fact]
    public void EveryCharacterGraphicHasEightRowsAndNothingElseDoes()
    {
        for (var code = 32; code <= 126; code++)
        {
            var bitmap = Font3.Bitmap(((char)code).ToString());
            Assert.NotNull(bitmap);
            Assert.Equal(8, bitmap.Length);
        }

        Assert.Null(Font3.Bitmap(" "[1..]));
        Assert.Null(Font3.Bitmap("ab"));
        Assert.Null(Font3.Bitmap(""));
    }

    // The solid block is all lit, the blank all dark, and the road
    // tips are single pixels in the corners the Standard names.
    [Fact]
    public void ThePixelsReadLeftToRightFromBitSeven()
    {
        var solid = Font3.Bitmap("6")!;
        var blank = Font3.Bitmap(" ")!;
        var topRight = Font3.Bitmap("G")!;
        var bottomLeft = Font3.Bitmap("I")!;

        for (var y = 0; y < Font3.Rows; y++)
        {
            for (var x = 0; x < Font3.Pixels; x++)
            {
                Assert.True(Font3.Lit(solid, x, y));
                Assert.False(Font3.Lit(blank, x, y));
                Assert.Equal((x, y) == (7, 0), Font3.Lit(topRight, x, y));
                Assert.Equal((x, y) == (0, 7), Font3.Lit(bottomLeft, x, y));
            }
        }
    }

    // The reverse twins at 123 to 126 are the spec's own inverted
    // bitmaps of the arrows and the question mark.
    [Theory]
    [InlineData("\\", "{")]
    [InlineData("]", "|")]
    [InlineData("^", "}")]
    [InlineData("`", "~")]
    public void TheReverseTwinsInvertTheirPlainShapes(string plain, string reversed)
    {
        var shape = Font3.Bitmap(plain)!;
        var twin = Font3.Bitmap(reversed)!;

        for (var y = 0; y < Font3.Rows; y++)
        {
            Assert.Equal((byte)~shape[y], twin[y]);
        }
    }
}
