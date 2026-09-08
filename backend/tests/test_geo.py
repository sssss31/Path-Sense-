from app.schemas.analysis import Coordinate
from app.utils.geo import distance_km,elevation_metrics,sample_fixed
def test_fixed_sampling_keeps_endpoints():
    points=[Coordinate(lat=26-i*.01,lng=91+i*.01) for i in range(20)];sample=sample_fixed(points,5)
    assert len(sample)==5 and sample[0]==points[0] and sample[-1]==points[-1]
def test_elevation_metrics():
    points=[Coordinate(lat=26,lng=91),Coordinate(lat=25.99,lng=91.01),Coordinate(lat=25.98,lng=91.02)]
    result=elevation_metrics([100,150,125],points)
    assert result["elevation_gain"]==50 and result["maximum_elevation"]==150

def test_nominatim_ranking_prefers_north_east_india():
    from app.providers.live import NominatimGeocodingProvider
    rows=[{"lat":"28.6","lon":"77.2","importance":.9,"display_name":"Delhi"},{"lat":"26.6","lon":"92.8","importance":.4,"display_name":"Tezpur, Assam"}]
    assert NominatimGeocodingProvider.rank(rows)[0]["display_name"]=="Tezpur, Assam"
