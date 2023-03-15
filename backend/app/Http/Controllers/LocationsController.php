<?php

namespace App\Http\Controllers;
use App\Models\Locations;
use Illuminate\Http\Request;

class LocationsController extends Controller
{
    public function index()
    {
        $locations = Locations::all();

        // Json Response
        return response()->json([
            'locations' => $locations
        ], 200);

    }

    public function show($id)
    {
        $locations = Locations::where('id', $id)->get();


        // Json Response
        return response()->json([
            'locations' => $locations
        ], 200);

    }


    public function store(Request $request)
    {
        try {
            // Create a location
            Locations::create([
                'name' => $request->name,
                'address1' => $request->address1,
                'address2' => $request->address2,
                'city' => $request->city,
                'state' => $request->state,
                'country' => $request->country,
                'zipcode' => $request->zipcode,
                'location_type' => $request->location_type,
            ]);

            // Return Json Response
            return response()->json(['message' => "Location added"], 200);
        }
         catch (\Exception $e) {
            // Return Json Response
            return response()->json(['message' => "Error adding location" . $e], 500);
        }
    }

    public function update(Request $request, $id)
    {
        if(!$request){
            return response()->json(['message' => "Error - Empty request" . $e], 500);
        }

        try {

            $location = Locations::find($id);
            if (!$location) {
                return response()->json(['message' => 'Location Not Found.'], 404);
            }

            //Update location
            $location->name = $request->name;
            $location->address1 = $request->address1;
            $location->address2 = $request->address2;
            $location->city = $request->city;
            $location->state = $request->state;
            $location->country = $request->country;
            $location->zipcode = $request->zipcode;
            $location->location_type = $request->location_type;
            $location->save();

            // Return Json Response
            return response()->json(['message' => "Location updated",
                'name' => $request->name,
                'address1' => $request->address1,
                'address2' => $request->address2,
                'city' => $request->city,
                'state' => $request->state,
                'country' => $request->country,
                'zipcode' => $request->zipcode,
                'location_type' => $request->location_type
             ], 200);
        }
         catch (\Exception $e) {
            // Return Json Response
            return response()->json(['message' => "Error updateing location" . $e], 500);
        }
    }


    public function destroy($id)
    {

        $locations = Locations::find($id);
        if (!$locations) {
            return response()->json(['message' => 'Entry not found.'], 404);
        }
        $locations->delete();
        // Return Json Response
        return response()->json(['message' => 'Record ' . $id . ' deleted'], 200);
    }

}
