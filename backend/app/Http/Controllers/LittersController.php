<?php

namespace App\Http\Controllers;

use App\Models\Litters;
use Illuminate\Http\Request;

class LittersController extends Controller
{

    public function index()
    {
        $litters = Litters::all();


        // Json Response
        return response()->json([
            'litters' => $litters
        ], 200);

    }

    public function show($id)
    {
        $litters = Litters::where('id', $id)->get();


        // Json Response
        return response()->json([
            'litters' => $litters
        ], 200);

    }


    public function store(Request $request)
    {
        try {
            // Create a Litter
            Litters::create([
                'date_of_litter' => $request->date_of_litter,
                'description' => $request->description,
                'is_active' => $request->is_active
            ]);

            // Return Json Response
            return response()->json(['message' => "Litter added"], 200);
        }
         catch (\Exception $e) {
            // Return Json Response
            return response()->json(['message' => "Error adding litter" . $e], 500);
        }
    }

    public function update(Request $request, $id)
    {
        if(!$request){
            return response()->json(['message' => "Error - Empty request" . $e], 500);
        }

        try {

            $litter = Litters::find($id);
            if (!$litter) {
                return response()->json(['message' => 'litter Not Found.'], 404);
            }

            //Update litter
            $litter->date_of_litter = $request->date_of_litter;
            $litter->description = $request->description;
            $litter->is_active = $request->is_active;
            $litter->save();

            // Return Json Response
            return response()->json(['message' => "litter updated"], 200);
        }
         catch (\Exception $e) {
            // Return Json Response
            return response()->json(['message' => "Error updateing litter" . $e], 500);
        }
    }

    public function destroy($id)
    {

        $litter = Litters::find($id);
        if (!$litter) {
            return response()->json(['message' => 'Entry not found.'], 404);
        }
        $litter->delete();
        // Return Json Response
        return response()->json(['message' => 'Record ' . $id . ' deleted'], 200);
    }


}
